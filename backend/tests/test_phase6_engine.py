"""Phase 6 safeguards use synthetic inputs and immutable dated public fixtures."""
from copy import deepcopy

import pytest

from app.valuation.assumptions import estimate_wacc
from app.valuation.automatic import prepare_automatic_inputs
from app.valuation.engine import calculate_valuation
from app.valuation.forecasts import derive_forward_forecasts
from app.valuation.schemas import ValuationRequest, ValuationResponse
from test_automatic_evidence_fixture import examples
from test_valuation_automatic_integration import inputs, observation
from test_valuation_engine import synthetic_inputs  # noqa: F401 - shared synthetic pytest fixture
from test_valuation_forecasts import example  # noqa: F401 - shared synthetic pytest fixture
from test_valuation_forecasts import set_metric
from test_valuation_historical_multiples import annual


def multi_request(**extra):
    return ValuationRequest(assumptions={"forward_eps": 5, "target_pe": 20,
                                         "forecast_revenue": 1000, "target_ev_revenue": 1},
                            enabled_models=["pe", "evRevenue"], weights={"pe": 1, "evRevenue": 1}, **extra)


def test_diagnostics_preserve_weighted_math_and_omit_unavailable_zero_estimates(synthetic_inputs):
    synthetic_inputs["financial_retrieved_at"] = "2026-01-05T00:00:00Z"
    result = calculate_valuation(synthetic_inputs, multi_request())
    base = result["scenarios"]["base"]
    assert base["summary"]["fair_value"] == pytest.approx((100 + 92) / 2)
    diagnostic = base["diagnostics"]
    assert diagnostic["coverage"]["contributing_models"] == ["pe", "evRevenue"]
    assert diagnostic["coverage"]["method_family_count"] == 2
    assert diagnostic["aggregation"]["estimate_range"] == {"minimum": 92, "maximum": 100}
    assert diagnostic["aggregation"]["dispersion"]["relative_spread"] == pytest.approx(0.08)
    assert diagnostic["aggregation"]["weight_source"] == "user"
    assert diagnostic["aggregation"]["per_model_weight_sources"] == {"pe": "user", "evRevenue": "user"}
    assert "do not establish independent evidence" in diagnostic["aggregation"]["warnings"][0]
    assert result["diagnostics"] == diagnostic
    assert result["data_completeness"] == base["data_completeness"]
    validated = ValuationResponse.model_validate(result).model_dump()
    assert validated["scenarios"]["base"]["diagnostics"] == diagnostic
    assert validated["engine_version"] == "1.1.0"


def test_unused_policy_defaults_and_unsuitable_affo_do_not_reduce_active_assumption_quality(synthetic_inputs):
    synthetic_inputs["financial_retrieved_at"] = "2026-01-05T00:00:00Z"
    result = calculate_valuation(synthetic_inputs, multi_request())
    confidence = result["confidence"]
    assert confidence["level"] == "moderate"
    assert confidence["contributing_policy_inputs"] == []
    assert "cost_of_equity" not in confidence["contributing_user_inputs"]
    assert result["defaults"]["base"]["metadata"]["cost_of_equity"]["evidence_type"] == "policy"
    assert result["diagnostics"]["coverage"]["applicable_count"] < 11


def test_related_earnings_models_do_not_create_false_independence(synthetic_inputs):
    result = calculate_valuation(synthetic_inputs, ValuationRequest(
        assumptions={"forward_eps": 5, "target_pe": 20, "earnings_growth": 0.1, "target_peg": 2},
        enabled_models=["pe", "peg"], weights={"pe": 1, "peg": 1}))
    diagnostic = result["diagnostics"]
    assert diagnostic["coverage"]["contributing_count"] == 2
    assert diagnostic["coverage"]["method_family_count"] == 1
    assert result["confidence"]["level"] == "low"
    assert {item["key"] for item in diagnostic["aggregation"]["shared_assumptions"]} >= {"forward_eps"}


def test_mixed_and_zero_user_weights_remain_explicit(synthetic_inputs):
    request = multi_request()
    request.weights = {"pe": 1}
    result = calculate_valuation(synthetic_inputs, request)
    assert result["diagnostics"]["aggregation"]["weight_source"] == "mixed"
    request.weights = {"pe": 0, "evRevenue": 1}
    result = calculate_valuation(synthetic_inputs, request)
    assert result["diagnostics"]["aggregation"]["estimate_range"] is None
    pe = next(item for item in result["diagnostics"]["coverage"]["excluded_models"] if item["model_id"] == "pe")
    assert pe["status"] == "disabled_or_zero_weight"
    assert result["configured_weights"]["pe"] == 0


@pytest.mark.parametrize("update", ["stale", "conflict", "dispersion", "negative"])
def test_weak_inputs_or_disagreement_cannot_receive_moderate_confidence(synthetic_inputs, update):
    synthetic_inputs["financial_retrieved_at"] = "2026-01-05T00:00:00Z"
    request = multi_request()
    if update == "stale":
        synthetic_inputs["reporting_period"]["end_date"] = "2020-12-31"
    elif update == "conflict":
        synthetic_inputs["warnings"].append({"field": "cash", "code": "incompatible_fact_period", "message": "Synthetic incompatible period"})
    elif update == "dispersion":
        request.assumptions["target_pe"] = 100
    else:
        synthetic_inputs["values"]["debt"] = 2000
    result = calculate_valuation(synthetic_inputs, request)
    assert result["confidence"]["level"] == "low"
    if update == "dispersion":
        assert result["diagnostics"]["aggregation"]["dispersion"]["status"] == "material_disagreement"
    if update == "negative":
        assert result["diagnostics"]["aggregation"]["estimate_range"]["minimum"] < 0


def test_freshness_assessment_reproduces_archived_snapshot(synthetic_inputs, monkeypatch):
    synthetic_inputs["financial_retrieved_at"] = "2026-01-05T00:00:00Z"
    before = calculate_valuation(synthetic_inputs, multi_request())["confidence"]
    class LaterDate:
        @classmethod
        def today(cls):
            raise AssertionError("A frozen snapshot must not depend on the wall clock")
    monkeypatch.setattr("app.valuation.confidence.date", LaterDate)
    after = calculate_valuation(synthetic_inputs, multi_request())["confidence"]
    assert after == before
    assert after["assessed_as_of"] == "2026-01-05"


@pytest.mark.parametrize("stale", ["status", "warning"])
def test_explicit_stale_financial_cache_overrides_original_snapshot_freshness(synthetic_inputs, stale):
    synthetic_inputs["financial_retrieved_at"] = "2026-01-05T00:00:00Z"
    if stale == "status":
        synthetic_inputs["data_status"] = "stale"
    else:
        synthetic_inputs["warnings"].append({"field": "financials", "code": "stale_provider_failure", "message": "Synthetic provider failure; retained cache stale"})
    result = calculate_valuation(synthetic_inputs, multi_request())
    assert result["confidence"]["level"] == "low"
    assert result["confidence"]["assessed_as_of"] == "2026-01-05"
    assert result["diagnostics"]["data_quality"]["level"] in {"limited", "unavailable"}
    factor = next(factor for factor in result["confidence"]["factors"] if factor["name"] == "Financial cache freshness")
    assert factor["status"] == "limited"


def test_all_eligibility_alternatives_explain_recoverable_inputs(synthetic_inputs):
    result = calculate_valuation(synthetic_inputs)
    fcfe = next(model for model in result["scenarios"]["base"]["models"] if model["id"] == "fcfe")
    paths = fcfe["eligibility"]["input_paths"]
    assert any("net_borrowing" in path["missing_inputs"] and "change_nwc" in path["missing_inputs"] for path in paths)
    assert any("projected_fcfe" in path["missing_inputs"] for path in paths)
    assert all(set(path["available_inputs"]).isdisjoint(path["missing_inputs"]) for path in paths)


def test_near_terminal_spread_is_disclosed_without_changing_formula(synthetic_inputs):
    result = calculate_valuation(synthetic_inputs, ValuationRequest(
        assumptions={"fcff": 100, "cash_flow_growth": 0, "forecast_years": 2,
                     "wacc": 0.020001, "terminal_growth": 0.02}, enabled_models=["fcff"]))
    model = next(model for model in result["scenarios"]["base"]["models"] if model["id"] == "fcff")
    assert model["status"] == "valid"
    assert model["details"]["discount_terminal_spread"] == pytest.approx(0.000001)
    assert any("one percentage point" in warning for warning in model["warnings"])
    assert result["confidence"]["level"] == "low"


@pytest.mark.parametrize("ticker,expected,count", [("AAPL", 214.2302568301956, 1), ("MSFT", 619.5604742486083, 1), ("NVDA", None, 0), ("ORCL", None, 0)])
def test_dated_company_fixtures_preserve_justified_pe_and_truthful_blockers(ticker, expected, count):
    original, evidence = examples()[ticker]
    before = deepcopy((original, evidence))
    prepared = prepare_automatic_inputs(original, evidence)
    result = calculate_valuation(prepared)
    summary = result["scenarios"]["base"]["summary"]
    assert summary["count"] == count
    assert summary["fair_value"] == (pytest.approx(expected) if expected is not None else None)
    assert result["confidence"]["level"] == ("low" if count else "unavailable")
    assert result["diagnostics"]["coverage"]["method_family_count"] == count
    assert (original, evidence) == before
    if ticker in {"AAPL", "MSFT", "NVDA"}:
        assert prepared["values"]["debt"] is None


@pytest.mark.parametrize("field", ["cash", "debt", "preferred_equity", "depreciation_and_amortization"])
def test_additional_amounts_cannot_mix_incompatible_financial_periods(field):
    original = inputs()
    reported = observation(25, observation_date="2023-12-31", scope_complete=True,
                           period={"start_date": "2023-01-01", "end_date": "2023-12-31"})
    result = prepare_automatic_inputs(original, {"observations": {field: reported}})
    assert result["values"].get(field) == original["values"].get(field)
    assert result["automatic_assumptions"][field]["value"] is None


def test_additional_amounts_require_original_identity_and_duration_scope():
    original = inputs()
    missing_source = observation(25)
    missing_source.pop("source_id")
    result = prepare_automatic_inputs(original, {"observations": {"cash": missing_source}})
    assert result["values"]["cash"] == original["values"]["cash"]
    result = prepare_automatic_inputs(original, {"observations": {"depreciation_and_amortization": observation(25)}})
    assert result["values"].get("depreciation_and_amortization") == original["values"].get("depreciation_and_amortization")


def test_additional_aligned_duration_and_explicit_claim_zero_remain_usable():
    original = inputs()
    period = deepcopy(original["reporting_period"])
    result = prepare_automatic_inputs(original, {"observations": {
        "depreciation_and_amortization": observation(25, period=period),
        "minority_interest": observation(0, scope_complete=True, period=period)}})
    assert result["values"]["depreciation_and_amortization"] == 25
    assert result["values"]["minority_interest"] == 0
    assert original["values"].get("depreciation_and_amortization") is None
    assert original["values"]["minority_interest"] is None


@pytest.mark.parametrize("complete,expected", [(False, None), (None, None), (True, 25)])
def test_non_sec_debt_identity_does_not_substitute_for_complete_scope(complete, expected):
    original = inputs()
    result = prepare_automatic_inputs(original, {"observations": {"debt": observation(25, scope_complete=complete)}})
    assert result["values"]["debt"] == expected


def test_share_observation_after_frozen_snapshot_never_changes_denominator():
    original = inputs()
    result = prepare_automatic_inputs(original, {"as_of_date": "2024-06-30", "observations": {
        "current_shares": observation(8, unit="shares", scope_verified=True, share_basis="dated_common_shares_outstanding")}})
    assert result["values"]["shares"] == original["values"]["shares"]
    assert result["automatic_assumptions"]["current_shares"]["value"] is None


def test_forecast_history_cannot_use_a_different_base_year(example):
    original, evidence = example
    original["reporting_period"] = {"start_date": "2024-01-01", "end_date": "2024-12-31"}
    result = derive_forward_forecasts(original, evidence)
    assert result["assumptions"] == {}
    assert result["forecast_quality"]["reason"] == "forecast_base_period_mismatch"


@pytest.mark.parametrize("last_year,usable", [(2024, False), (2025, True)])
def test_working_capital_and_financing_forecasts_require_selected_base_year(example, last_year, usable):
    original, evidence = example
    working = [annual(year) for year in range(last_year - 2, last_year + 1)]
    financing = deepcopy(working)
    for index, (capital, funding) in enumerate(zip(working, financing)):
        set_metric(capital, "operating_current_assets", 300 + index * 20)
        set_metric(capital, "operating_current_liabilities", 200)
        set_metric(funding, "debt_issuance", 50 + index * 10)
        set_metric(funding, "debt_principal_repayments", 20)
    evidence["operating_working_capital_periods"] = working
    evidence["financing_periods"] = financing
    result = derive_forward_forecasts(original, evidence)
    assert ("nwc_ratio" in result["assumptions"]) is usable
    assert ("change_nwc" in result["assumptions"]) is usable
    assert ("net_borrowing" in result["assumptions"]) is usable


@pytest.mark.parametrize("invalid", ["scope", "future_publication", "currency"])
def test_unusable_latest_cash_flow_evidence_does_not_fall_back_to_older_base(example, invalid):
    original, evidence = example
    working = [annual(year) for year in range(2022, 2026)]
    financing = deepcopy(working)
    for index, (capital, funding) in enumerate(zip(working, financing)):
        set_metric(capital, "operating_current_assets", 300 + index * 20)
        set_metric(capital, "operating_current_liabilities", 200)
        set_metric(funding, "debt_issuance", 50 + index * 10)
        set_metric(funding, "debt_principal_repayments", 20)
    for rows, field in ((working, "operating_current_assets"), (financing, "debt_issuance")):
        if invalid == "scope":
            rows[-1]["facts"][field]["scope_complete"] = False
        elif invalid == "future_publication":
            rows[-1]["facts"][field]["provenance"][0]["filed"] = "2200-01-01"
        else:
            rows[-1]["currency"] = "EUR"
    evidence["operating_working_capital_periods"] = working
    evidence["financing_periods"] = financing
    result = derive_forward_forecasts(original, evidence)
    assert "nwc_ratio" not in result["assumptions"]
    assert "change_nwc" not in result["assumptions"]
    assert "net_borrowing" not in result["assumptions"]


@pytest.mark.parametrize("gap,basis,allowed", [(7, "market_value", True), (8, "market_value", False),
                                               (550, "book_value", True), (551, "book_value", False), (-1, "book_value", False)])
def test_wacc_does_not_mix_incompatible_capital_observations(gap, basis, allowed):
    from datetime import date, timedelta
    equity_date = date(2026, 1, 1)
    source = {"source": "Synthetic dated capital observation", "currency": "USD"}
    equity = {**source, "value": 800, "basis": "market_value", "observation_date": equity_date.isoformat()}
    debt = {**source, "value": 200, "basis": basis, "observation_date": (equity_date - timedelta(days=gap)).isoformat()}
    rate = {**source, "value": 0.05, "method": "Synthetic yield", "observation_date": equity_date.isoformat()}
    if allowed:
        assert estimate_wacc(0.1, rate, 0.25, equity, debt, allow_book_debt=True)["value"] == pytest.approx(0.0875)
    else:
        with pytest.raises(ValueError, match="calendar days|550 days"):
            estimate_wacc(0.1, rate, 0.25, equity, debt, allow_book_debt=True)
