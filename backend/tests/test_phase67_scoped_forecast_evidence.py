"""Complete-scope synthetic histories, never evidence of live stock coverage."""
from copy import deepcopy
from datetime import UTC, datetime
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.core.exceptions import ApiError
from app.services import automatic_inputs_service
from app.services.automatic_inputs_service import AutomaticInputsService, scoped_forecast_periods
from app.services.cache_service import CachedResult
from app.valuation.automatic import prepare_automatic_inputs
from app.valuation.engine import calculate_valuation
from app.valuation.forecasts import derive_forward_forecasts
from test_valuation_historical_multiples import annual


@pytest.fixture
def captured(monkeypatch):
    """Only tests may install this explicitly synthetic scope contract."""
    fixture = json.loads((Path(__file__).parent / "fixtures/valuation/phase67_scoped_forecast_history.json").read_text())
    mapping = {(source["taxonomy"], source["concept"]): {
        "field": field, "financial_scope": source["financial_scope"],
        "methodology_version": "synthetic-contract-test-1", "authority": "synthetic-unit-test-only"}
        for field, sources in fixture["annual"][0]["provenance"].items() for source in sources
        if field in automatic_inputs_service.FORECAST_SCOPES}
    monkeypatch.setattr(automatic_inputs_service, "REVIEWED_FORECAST_SCOPE_CONCEPTS", mapping)
    return fixture


def scoped(captured):
    return scoped_forecast_periods(captured, captured["company"], captured["retrieved_at"], source_payload=captured["raw_source"])


def raw_observation(captured, index, field):
    source = captured["annual"][index]["provenance"][field][0]
    records = captured["raw_source"]["facts"][source["taxonomy"]][source["concept"]]["units"][source["unit"]]
    return next(record for record in records if record["end"] == captured["annual"][index]["end_date"])


def forecasting_inputs(captured):
    periods = [annual(year) for year in range(2020, 2026)]
    return {"company": deepcopy(captured["company"]), "currency": "USD", "financial_retrieved_at": captured["retrieved_at"],
            "reporting_period": {key: periods[-1][key] for key in ("fiscal_year", "fiscal_period", "start_date", "end_date")},
            "annual_periods": periods, "facts": deepcopy(periods[-1]["facts"]), "values": {"revenue": 1000, "trailing_eps": 10},
            "basis": {"share_basis_verified": True, "income_earnings_basis_verified": True}}


def test_complete_annotated_histories_preserve_sources_and_enable_only_their_forecasts(captured):
    original = deepcopy(captured)
    result = scoped(captured)
    assert len(result["operating_working_capital_periods"]) == len(result["financing_periods"]) == 3
    assert result["forecast_scope_diagnostics"] == []
    inputs = forecasting_inputs(captured)
    evidence = {**result, "historical_annual_periods": inputs["annual_periods"], "as_of_date": "2026-03-01",
                "splits": {"complete": True, "splits": []}}
    records = derive_forward_forecasts(inputs, evidence)["assumptions"]
    assert records["nwc_ratio"]["value"] == pytest.approx(.12)
    assert records["change_nwc"]["value"] == 20
    assert records["net_borrowing"]["value"] == 30
    assert records["net_borrowing"]["evidence_type"] == "estimate"
    assert "constant_annual_net_borrowing" in records["net_borrowing"]["policy_dependencies"]
    source = result["financing_periods"][0]["facts"]["debt_issuance"]["provenance"]
    assert source == captured["annual"][0]["provenance"]["debt_issuance"]
    assert captured == original


@pytest.mark.parametrize("change", [
    {"scope_complete": False}, {"financial_scope": "long_term_debt_only"}, {"unit": "EUR"},
    {"start": "2024-07-01"}, {"end": "2024-09-30"}, {"filed": "2200-02-04"},
    {"form": "10-Q"}, {"fy": 2023}, {"accn": None}, {"value": 999},
    {"cik": "0000000002"}, {"derivation": "change_in_debt_balance"}, {"metric": "long_term_debt_proceeds"},
    {"value_state": "unavailable"}, {"value_state": "unknown"}, {"value_state": "verified_zero"},
])
def test_incomplete_incompatible_or_partial_financing_is_not_a_complete_flow(captured, change):
    captured["annual"][1]["provenance"]["debt_issuance"][0].update(change)
    result = scoped(captured)
    assert len(result["financing_periods"]) == 2
    assert len(result["operating_working_capital_periods"]) == 3
    assert any(item["fiscal_year"] == 2024 and "debt_issuance" in item["missing_inputs"]
               for item in result["forecast_scope_diagnostics"])


@pytest.mark.parametrize("change", [{"start": "2024-01-01"}, {"scope_complete": False},
                                    {"financial_scope": "total_current_assets"}, {"value": float("nan")}])
def test_incomplete_or_duration_operating_balance_never_establishes_nwc(captured, change):
    captured["annual"][1]["provenance"]["operating_current_assets"][0].update(change)
    assert len(scoped(captured)["operating_working_capital_periods"]) == 2


def test_no_partial_fields_or_absent_values_become_zero(captured):
    for period in captured["annual"]:
        period["metrics"].pop("debt_issuance")
        period["provenance"].pop("debt_issuance")
        period["metrics"]["long_term_debt_proceeds"] = 60
        period["metrics"]["accounts_receivable"] = 300
        period["metrics"].pop("operating_current_assets")
    result = scoped(captured)
    assert result["financing_periods"] == result["operating_working_capital_periods"] == []
    assert all(item["code"] == "required_metric_missing" for item in result["forecast_scope_diagnostics"])


@pytest.mark.parametrize("value", [None, -1, True, float("inf"), float("nan")])
def test_nonfinite_negative_boolean_and_absent_aggregate_values_stay_unavailable(captured, value):
    captured["annual"][1]["metrics"]["debt_issuance"] = value
    assert len(scoped(captured)["financing_periods"]) == 2


def test_zero_requires_explicit_verified_zero_source_state(captured):
    for period in captured["annual"]:
        period["metrics"]["debt_issuance"] = 0
        source = period["provenance"]["debt_issuance"][0]
        source.update(value=0, val=0, value_state="unknown")
    for index in range(3):
        raw_observation(captured, index, "debt_issuance")["val"] = 0
    assert scoped(captured)["financing_periods"] == []
    for period in captured["annual"]:
        period["provenance"]["debt_issuance"][0]["value_state"] = "verified_zero"
    assert len(scoped(captured)["financing_periods"]) == 3


def test_mixed_publication_and_revenue_contexts_do_not_form_one_history(captured):
    captured["annual"][0]["provenance"]["debt_issuance"][0]["accn"] = "0000000001-24-000002"
    captured["annual"][0]["provenance"]["revenue"][0]["accn"] = "0000000001-24-000003"
    raw_observation(captured, 0, "debt_issuance")["accn"] = "0000000001-24-000002"
    raw_observation(captured, 0, "revenue")["accn"] = "0000000001-24-000003"
    result = scoped(captured)
    assert len(result["financing_periods"]) == len(result["operating_working_capital_periods"]) == 2
    assert all(item["code"] == "period_mismatch" for item in result["forecast_scope_diagnostics"])


@pytest.mark.parametrize("identity_change", [{"cik": "0000000002"}, {"issuer_id": "another-issuer"},
                                             {"instrument_id": "another-class"}, {"listing_id": "another-listing"}])
def test_scoped_history_cannot_cross_issuer_class_or_listing(captured, identity_change):
    inputs = forecasting_inputs(captured)
    evidence = {**scoped(captured), "historical_annual_periods": inputs["annual_periods"], "as_of_date": "2026-03-01"}
    evidence["forecast_evidence_identity"].update(identity_change)
    original = deepcopy((inputs, evidence))
    result = derive_forward_forecasts(inputs, evidence)
    assert "net_borrowing" not in result["assumptions"]
    assert "nwc_ratio" not in result["assumptions"]
    assert result["forecast_quality"]["scoped_history_status"] == "incompatible_financial_identity"
    assert (inputs, evidence) == original


def test_old_history_is_not_substituted_for_the_selected_base(captured):
    inputs = forecasting_inputs(captured)
    inputs["reporting_period"].update(fiscal_year=2026, start_date="2026-01-01", end_date="2026-12-31")
    evidence = {**scoped(captured), "historical_annual_periods": inputs["annual_periods"], "as_of_date": "2026-03-01"}
    result = derive_forward_forecasts(inputs, evidence)
    assert result["assumptions"] == {}
    assert result["forecast_quality"]["reason"] == "forecast_base_period_mismatch"


@pytest.mark.parametrize("source_cik", [None, 2, "invalid"])
def test_missing_or_wrong_reporting_issuer_cannot_support_scoped_history(captured, source_cik):
    raw = {**captured["raw_source"], "cik": source_cik}
    result = scoped_forecast_periods(captured, captured["company"], captured["retrieved_at"], source_payload=raw)
    assert result["financing_periods"] == result["operating_working_capital_periods"] == []
    assert result["forecast_scope_diagnostics"][0]["code"] == "financial_identity_or_snapshot_unverified"


@pytest.mark.asyncio
async def test_service_wires_the_scoped_histories_without_provider_requests(captured):
    inputs = forecasting_inputs(captured)
    requests = []
    class Cache:
        async def get_or_load(self, key, *_args):
            requests.append(key)
            payload = captured["raw_source"] if key.startswith("sec:facts:") else inputs["annual_periods"]
            return CachedResult(deepcopy(payload), "fresh", datetime(2026, 3, 1, tzinfo=UTC), [])
    service = AutomaticInputsService(SimpleNamespace(cache=Cache()), None, Settings(_env_file=None))
    async def prices(*_args):
        return {"prices": [], "status": "unavailable"}
    async def splits(*_args):
        return {"splits": [], "status": "unavailable", "complete": False}
    async def empty(*_args):
        return {}
    service._prices, service._splits = prices, splits
    service._treasury = service._beta = service._supplemental = empty
    original = deepcopy(captured)
    result = await service.evidence("SYN", {"company": captured["company"]}, captured, captured["retrieved_at"])
    assert len(requests) == 2
    assert len(result["financing_periods"]) == len(result["operating_working_capital_periods"]) == 3
    prepared = prepare_automatic_inputs(inputs, result)
    assert prepared["automatic_assumptions"]["net_borrowing"]["value"] == 30
    assert prepared["automatic_assumptions"]["nwc_ratio"]["value"] == pytest.approx(.12)
    assert captured == original


@pytest.mark.asyncio
async def test_mismatched_retained_raw_issuer_is_rejected_before_optional_work(captured):
    requests = []
    class Cache:
        async def get_or_load(self, key, *_args):
            requests.append(key)
            return CachedResult({"cik": 2, "facts": {}}, "fresh", datetime(2026, 3, 1, tzinfo=UTC), [])
    service = AutomaticInputsService(SimpleNamespace(cache=Cache()), None, Settings(_env_file=None))
    with pytest.raises(ApiError) as failure:
        await service.evidence("SYN", {"company": captured["company"]}, captured, captured["retrieved_at"])
    assert failure.value.code == "incompatible_financial_identity"
    assert len(requests) == 1


@pytest.mark.parametrize("ticker,expected", [("AAPL", 214.2302568301956), ("MSFT", 619.5604742486083),
                                            ("NVDA", None), ("ORCL", None)])
def test_retained_company_defaults_do_not_gain_unverified_scope(ticker, expected):
    from phase6_company_helpers import phase6_company_inputs, source_examples
    inputs, evidence, _ = phase6_company_inputs(ticker)
    originals, _, _ = source_examples()
    original = originals[ticker]
    scope = scoped_forecast_periods(original["normalized"], original["profile"]["company"], original["retrieved_at"],
                                    source_payload={"cik": original["profile"]["company"]["cik"], "facts": {}})
    assert scope["financing_periods"] == scope["operating_working_capital_periods"] == []
    result = calculate_valuation(prepare_automatic_inputs(inputs, {**evidence, **scope}))
    summary = result["scenarios"]["base"]["summary"]
    assert summary["fair_value"] == (pytest.approx(expected) if expected is not None else None)
    assert summary["count"] == (1 if expected is not None else 0)


def test_production_scope_mapping_admits_no_unaudited_financial_concepts():
    assert automatic_inputs_service.REVIEWED_FORECAST_SCOPE_CONCEPTS == {}


def test_complete_source_annotations_cannot_replace_a_reviewed_contract(captured, monkeypatch):
    monkeypatch.setattr(automatic_inputs_service, "REVIEWED_FORECAST_SCOPE_CONCEPTS", {})
    # Even a provider-supplied copy of an apparent allowlist is untrusted data.
    captured["raw_source"]["reviewed_scope_concepts"] = {"ReviewedDebtIssuance": "complete_conventional_debt_issuance"}
    result = scoped(captured)
    assert result["operating_working_capital_periods"] == result["financing_periods"] == []
    assert all(item["code"] == "required_metric_missing" for item in result["forecast_scope_diagnostics"])


def test_unknown_or_economically_unrelated_concept_cannot_inherit_scope_flags(captured):
    source = captured["annual"][1]["provenance"]["debt_issuance"][0]
    original = deepcopy(raw_observation(captured, 1, "debt_issuance"))
    source["concept"] = "UnrelatedCashBalance"
    captured["raw_source"]["facts"][source["taxonomy"]][source["concept"]] = {"units": {"USD": [original]}}
    assert len(scoped(captured)["financing_periods"]) == 2


@pytest.mark.parametrize("change", [
    {"val": 61}, {"unit": "EUR"}, {"end": "2024-09-30"}, {"start": "2024-07-01"},
    {"accn": "0000000001-25-000002"}, {"filed": "2025-02-05"}, {"form": "10-Q"},
])
def test_original_observation_must_match_the_frozen_raw_snapshot(captured, change):
    raw = raw_observation(captured, 1, "debt_issuance")
    if "unit" in change:
        source = captured["annual"][1]["provenance"]["debt_issuance"][0]
        units = captured["raw_source"]["facts"][source["taxonomy"]][source["concept"]]["units"]
        units["USD"].remove(raw)
        units["EUR"] = [raw]
    else:
        raw.update(change)
    assert len(scoped(captured)["financing_periods"]) == 2


def test_forged_revenue_provenance_cannot_change_the_working_capital_ratio(captured):
    period = captured["annual"][1]
    period["metrics"]["revenue"] = 900
    period["provenance"]["revenue"][0].update(value=900, val=900)
    result = scoped(captured)
    assert len(result["operating_working_capital_periods"]) == 2
    assert len(result["financing_periods"]) == 3


def test_conflicting_raw_values_cannot_be_cherry_picked_as_a_complete_aggregate(captured):
    source = captured["annual"][1]["provenance"]["debt_issuance"][0]
    rows = captured["raw_source"]["facts"][source["taxonomy"]][source["concept"]]["units"]["USD"]
    rows.append({**deepcopy(raw_observation(captured, 1, "debt_issuance")), "val": 81})
    assert len(scoped(captured)["financing_periods"]) == 2
