"""Independent integration assertions, with synthetic financial observations."""
import pytest

from app.valuation.automatic import cost_of_debt_from_history, prepare_automatic_inputs
from app.valuation.engine import calculate_valuation
from app.valuation.inputs import build_valuation_inputs, normalize_annual_period
from app.valuation.models.fcff_dcf import calculate as calculate_fcff
from app.valuation.schemas import ValuationRequest
from test_valuation_inputs_history import synthetic_period


def inputs():
    return build_valuation_inputs({"company": {"ticker": "SYN", "is_bank": False, "is_reit": False,
                                               "has_multiple_share_classes": False}},
                                  {"currency": "USD", "annual": [synthetic_period()]})


def observation(value, **extra):
    return {"value": value, "unit": "USD", "state": "verified_zero" if value == 0 else "verified_value",
            "source_provider": "synthetic test", "source_type": "reported", "kind": "fact",
            "observation_date": "2024-12-31", "source_id": "synthetic:2024", **extra}


@pytest.mark.parametrize("state,complete,expected", [("unknown", True, None), ("verified_zero", False, None), ("verified_zero", True, 0)])
def test_verified_zero_requires_explicit_complete_scope(state, complete, expected):
    original = inputs()
    evidence = {"observations": {"preferred_equity": observation(0, state=state, scope_complete=complete)}}
    result = prepare_automatic_inputs(original, evidence)
    assert result["values"]["preferred_equity"] == expected
    assert calculate_valuation(result)["scenarios"]["base"]["assumptions"]["values"]["preferred_equity"] == expected
    assert result["automatic_assumptions"]["preferred_equity"]["input_status"] == ("verified_zero" if expected == 0 else "unknown")
    assert original["values"]["preferred_equity"] is None


@pytest.mark.parametrize("change", [{"unit": "EUR"}, {"observation_date": "2200-01-01"}, {"value": float("nan")}, {"state": "unknown"}])
def test_unusable_extra_observations_cannot_replace_financial_inputs(change):
    original = inputs()
    result = prepare_automatic_inputs(original, {"observations": {"debt": {**observation(50), **change}}})
    assert result["values"].get("debt") is None
    assert calculate_valuation(result)["scenarios"]["base"]["assumptions"]["values"]["debt"] is None


def test_dated_common_shares_do_not_recompute_historical_income_basis_or_overwrite_facts():
    original = inputs()
    result = prepare_automatic_inputs(original, {"observations": {"current_shares": observation(8, unit="shares", scope_verified=True, share_basis="dated_common_shares_outstanding")}})
    assert result["values"]["shares"] == 8
    assert result["facts"]["weighted_average_diluted_shares"]["value"] == 10
    assert result["basis"]["income_earnings_basis_verified"] is True
    assert result["basis"]["valuation_share_observation_date"] == "2024-12-31"
    blocked = prepare_automatic_inputs(original, {"observations": {"current_shares": observation(8, unit="shares", scope_verified=False)}})
    assert blocked["values"]["shares"] == 10


def test_cost_of_debt_uses_compatible_average_complete_debt_and_retains_proxy_warning():
    periods = [normalize_annual_period(synthetic_period(year=2023, metrics={"total_debt": 200}), "USD"),
               normalize_annual_period(synthetic_period(year=2024, metrics={"total_debt": 300, "interest_expense": 25}), "USD")]
    result = cost_of_debt_from_history(periods)
    assert result["value"] == pytest.approx(25 / ((200 + 300) / 2))
    assert result["evidence_type"] == "estimate"
    assert "not a current market" in result["source_description"]
    periods[0]["metrics"]["total_debt"] = None
    assert cost_of_debt_from_history(periods)["value"] is None


def test_provenance_classification_and_user_override_composition_are_additive():
    result = calculate_valuation(inputs(), ValuationRequest(assumptions={"forward_eps": 11, "target_pe": 20}, enabled_models=["pe"]))
    base = result["scenarios"]["base"]
    assert base["summary"]["fair_value"] == 220
    assert base["summary"]["classification"] == "user_defined"
    assert base["summary"]["composition"] == [{"classification": "user_defined", "weight": 1, "model_ids": ["pe"]}]
    assert "Single-model" in " ".join(base["summary"]["source_warnings"])
    for field in ("forward_eps", "target_pe", "cost_of_equity"):
        record = base["assumptions"]["metadata"][field]
        assert {"value", "unit", "source_category", "source_provider", "observation_date", "financial_period", "derivation_formula", "quality", "evidence_type", "editable", "source_identifiers"} <= set(record)
    assert result["assumption_methodology_version"] == "automatic-assumptions-2"


def test_unused_global_policy_rate_does_not_make_evidence_supported_pe_policy_based():
    original = inputs()
    original["automatic_assumptions"] = {key: {"value": value, "unit": "multiple" if key == "target_pe" else "fraction",
                                                 "source_type": "historical_estimate", "evidence_type": "estimate",
                                                 "source_provider": "synthetic historical observations", "warnings": []}
                                       for key, value in (("target_pe", 20), ("earnings_growth", 0.1))}
    result = calculate_valuation(original, ValuationRequest(enabled_models=["pe"]))
    assert result["scenarios"]["base"]["summary"]["fair_value"] == pytest.approx(220)
    assert result["scenarios"]["base"]["summary"]["classification"] == "evidence_supported"
    assert result["scenarios"]["bear"]["summary"]["classification"] == "policy_based"


def test_explicit_revenue_path_uses_actual_incremental_working_capital_and_terminal_reinvestment():
    values = {"revenue": 1000, "projected_revenue": [1100, 1200], "operating_margin": 0.2, "tax_rate": 0.25,
              "da_ratio": 0.02, "capex_ratio": 0.03, "nwc_ratio": 0.1, "wacc": 0.1,
              "terminal_growth": 0, "forecast_years": 2, "shares": 10, "debt": 0, "cash": 0,
              "preferred_equity": 0, "minority_interest": 0, "other_nonoperating_assets": 0}
    # Year 1: 165 + 22 - 33 - 10 = 144; year 2: 180 + 24 - 36 - 10 = 158.
    # Terminal at zero growth: 180 + 24 - 36 - 0 = 168, capitalized at 10%.
    expected = (144 / 1.1 + 158 / 1.1 ** 2 + (168 / 0.1) / 1.1 ** 2) / 10
    result = calculate_fcff(values)
    assert result["status"] == "valid"
    assert result["fair_value"] == pytest.approx(expected)
    assert [row["change_nwc"] for row in result["details"]["projection"]] == [10, 10]
    wrong_length = calculate_fcff({**values, "projected_revenue": [1100]})
    assert wrong_length["status"] == "invalid_input"


@pytest.mark.parametrize("series", [[0], [-1], [float("inf")], [True]])
def test_explicit_revenue_request_rejects_nonpositive_or_nonfinite_series(series):
    with pytest.raises(ValueError):
        ValuationRequest(assumptions={"projected_revenue": series})


@pytest.fixture
def automatic_examples():
    from test_automatic_evidence_fixture import examples
    return {ticker: prepare_automatic_inputs(data, evidence) for ticker, (data, evidence) in examples().items()}


@pytest.mark.parametrize("ticker,expected", [("AAPL", 214.2302568301956), ("MSFT", 619.5604742486083)])
def test_actual_default_activation_and_single_model_policy_composition(automatic_examples, ticker, expected):
    result = calculate_valuation(automatic_examples[ticker])
    base = result["scenarios"]["base"]
    assert base["summary"]["fair_value"] == pytest.approx(expected)
    assert base["summary"]["classification"] == "policy_based"
    assert base["summary"]["effective_weights"] == {"pe": 1}
    assert base["summary"]["count"] == 1


@pytest.mark.parametrize("field,dependent", [("earnings_growth", ["forward_eps"]),
                                            ("revenue_growth", ["forecast_revenue", "forecast_ebitda", "projected_revenue"]),
                                            ("ebitda_margin", ["forecast_ebitda"])])
def test_cleared_dependency_never_restores_a_cached_automatic_forecast(automatic_examples, field, dependent):
    result = calculate_valuation(automatic_examples["AAPL"], ValuationRequest(assumptions={field: None}))
    metadata = result["scenarios"]["base"]["assumptions"]["metadata"]
    assert all(metadata[key]["value"] is None for key in dependent)
    if field == "earnings_growth":
        assert result["scenarios"]["base"]["summary"]["fair_value"] is None


def test_scenario_clear_and_explicit_forecast_overrides_remain_independent(automatic_examples):
    data = automatic_examples["AAPL"]
    initial = calculate_valuation(data)
    edited = calculate_valuation(data, ValuationRequest(scenario_overrides={"base": {"earnings_growth": None}}))
    assert edited["scenarios"]["base"]["summary"]["fair_value"] is None
    for case in ("bear", "bull"):
        assert edited["scenarios"][case]["summary"]["fair_value"] == initial["scenarios"][case]["summary"]["fair_value"]
    explicit = calculate_valuation(data, ValuationRequest(assumptions={"earnings_growth": None, "forward_eps": 10}))
    assert explicit["scenarios"]["base"]["summary"]["fair_value"] == pytest.approx(10 * initial["scenarios"]["base"]["assumptions"]["values"]["target_pe"])
    assert explicit["scenarios"]["base"]["summary"]["classification"] == "user_defined"


def test_automatic_quality_preferences_do_not_multiply_correlated_family_evidence():
    from app.valuation.weighting import suggest_weights
    def model(identifier, quality):
        return {"id": identifier, "status": "valid", "eligibility": {"status": "eligible"},
                "source_quality": {"level": quality, "automatic_evidence": True}}
    alone, reason = suggest_weights([model("pe", "low")])
    together, _ = suggest_weights([model("pe", "low"), model("peg", "low")])
    better, _ = suggest_weights([model("pe", "moderate")])
    assert alone["pe"] == pytest.approx(25 * 0.6)
    assert sum(together.values()) == pytest.approx(sum(alone.values()))
    assert better["pe"] > alone["pe"]
    assert "not a probability" in reason["pe"]


def test_growth_provenance_uses_earnings_sources_and_debt_proxy_rejects_bad_calendars(automatic_examples):
    result = calculate_valuation(automatic_examples["AAPL"])
    record = result["scenarios"]["base"]["assumptions"]["metadata"]["earnings_growth"]
    eps_dates = {source["filed"] for period in automatic_examples["AAPL"]["annual_periods"]
                 for field in ("diluted_eps", "weighted_average_diluted_shares") for source in period["facts"].get(field, {}).get("provenance", [])}
    assert record["observation_date"] in eps_dates
    periods = [normalize_annual_period(synthetic_period(year=2023, metrics={"total_debt": 200}), "USD"),
               normalize_annual_period(synthetic_period(year=2024, metrics={"total_debt": 300, "interest_expense": 25}), "USD")]
    periods[1]["start_date"] = "2024-05-01"
    assert cost_of_debt_from_history(periods)["value"] is None


def test_explicit_structured_discount_sources_remain_user_provenance():
    result = calculate_valuation(inputs(), ValuationRequest(discount_rates={
        "risk_free_rate": {"value": 0.04, "source": "Synthetic Treasury observation", "observation_date": "2024-12-31"},
        "beta": {"value": 1.2, "source": "Synthetic estimate", "observation_date": "2024-12-31", "method": "Synthetic aligned return regression"},
        "equity_risk_premium": {"value": 0.05, "source": "Synthetic research policy", "observation_date": "2024-12-31"},
    }))
    metadata = result["scenarios"]["base"]["assumptions"]["metadata"]
    assert metadata["cost_of_equity"]["value"] == pytest.approx(0.1)
    for field in ("risk_free_rate", "beta", "equity_risk_premium", "cost_of_equity"):
        assert metadata[field]["evidence_type"] == "user"
    assert metadata["beta"]["observation_date"] == "2024-12-31"
    assert metadata["beta"]["source_provider"] == "Synthetic estimate"
