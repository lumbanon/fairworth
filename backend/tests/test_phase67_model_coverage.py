"""Coverage explains exact engine decisions and never changes their values."""
from copy import deepcopy
import pytest

from app.valuation.coverage import compatibility, enrich_valuation_coverage, summarize_coverage
from app.valuation.engine import calculate_valuation
from app.valuation.schemas import MODEL_IDS, ValuationRequest
from test_ai_evidence_context import retained_inputs
from test_api import client  # noqa: F401 -- shared isolated API fixture


@pytest.mark.parametrize("symbol", ["AAPL", "MSFT", "NVDA", "ORCL"])
def test_coverage_preserves_all_engine_outputs_and_exact_retained_defaults(symbol):
    inputs = retained_inputs()[symbol]
    before = deepcopy(inputs)
    original = calculate_valuation(inputs)
    result = enrich_valuation_coverage(inputs, original)
    assert inputs == before
    assert "financial_coverage" not in original
    assert len(result["financial_coverage"]["models"]) == 11
    for name, case in result["scenarios"].items():
        assert case["summary"] == original["scenarios"][name]["summary"]
        assert case["assumptions"] == original["scenarios"][name]["assumptions"]
        for index, model in enumerate(case["models"]):
            reference = original["scenarios"][name]["models"][index]
            assert model["fair_value"] == reference["fair_value"]
            assert model["eligibility"]["status"] == reference["eligibility"]["status"]
            assert bool(model["eligibility"]["blockers"]) is (model["status"] != "valid")
    expected = {"AAPL": 214.2302568301956, "MSFT": 619.5604742486083}
    assert result["scenarios"]["base"]["summary"]["fair_value"] == expected.get(symbol)


def test_every_alternative_path_and_missing_category_is_retained():
    inputs = retained_inputs()["MSFT"]
    result = enrich_valuation_coverage(inputs, calculate_valuation(inputs))
    model = next(row for row in result["financial_coverage"]["models"] if row["id"] == "fcff")
    assert len(model["required_inputs"]) == 5
    assert len(model["input_paths"]) == 5
    codes = {item["code"] for item in model["blockers"]}
    assert {"discount_rate_unavailable", "required_metric_missing"} <= codes
    pe = next(row for row in result["financial_coverage"]["models"] if row["id"] == "pe")
    assert pe["blockers"] == []
    assert result["financial_coverage"]["contributing_model_families"] == ["earnings"]


def test_quote_uses_observation_date_never_retrieval_or_manual_value():
    from datetime import UTC, datetime
    inputs = retained_inputs()["MSFT"]
    inputs.pop("market", None)
    clock = datetime(2026, 10, 20, 12, tzinfo=UTC)
    market = {"price": 100, "currency": "USD", "status": "fresh", "source_type": "provider",
              "price_timestamp": "2026-01-01T12:00:00Z", "retrieved_at": clock.isoformat()}
    assert compatibility(inputs, market, clock)["market_price"]["status"] == "stale"
    market["price_timestamp"] = "2026-10-20T11:00:00Z"
    assert compatibility(inputs, market, clock)["market_price"]["status"] == "available"
    market["source_type"] = "user"
    assert compatibility(inputs, market, clock)["market_price"]["status"] != "available"
    market["source_type"], market["price_timestamp"] = "provider", "2026-10-21T11:00:00Z"
    assert compatibility(inputs, market, clock)["market_price"]["status"] == "unavailable"


def test_api_publishes_all_blockers_periods_and_scoped_metadata(client):
    response = client.get("/api/stocks/MSFT/valuation/defaults")
    assert response.status_code == 200
    result = response.json()
    assert {row["id"] for row in result["financial_coverage"]["models"]} == set(MODEL_IDS)
    assert result["data_completeness"]["reporting_periods"]
    assert "source_identifiers" in result["data_completeness"]["reporting_periods"][0]
    assert set(result["data_completeness"]["compatibility"]) == {"share_basis", "currency", "reporting_regime", "market_price"}
    assert all("blockers" in model["eligibility"] for model in result["scenarios"]["base"]["models"])


def test_summary_rejects_cross_mode_and_duplicate_listing_denominators():
    sample = {"identity": {"listing_id": "fixture-listing"}, "data_mode": "mocked", "stages": {}}
    with pytest.raises(ValueError, match="Different financial evidence modes"):
        summarize_coverage([sample], as_of="2026-10-20T00:00:00Z", data_mode="retained_public")
    with pytest.raises(ValueError, match="stable listing"):
        summarize_coverage([sample, sample], as_of="2026-10-20T00:00:00Z", data_mode="mocked")
    sample["as_of"] = "2026-10-21T00:00:00Z"
    with pytest.raises(ValueError, match="aggregate audit clock"):
        summarize_coverage([sample], as_of="2026-10-20T00:00:00Z", data_mode="mocked")


def test_unused_cashflow_paths_are_not_reported_as_blocking_components():
    from app.valuation.coverage import model_blockers
    model = {"id": "fcff", "status": "unavailable", "eligibility": {
        "status": "unavailable", "reason_codes": ["missing_inputs"], "missing_inputs": ["wacc"],
        "input_paths": [{"missing_inputs": ["wacc"]}]}}
    blockers = model_blockers({"annual_periods": [{"fiscal_year": 2025}]}, model)
    assert [row["code"] for row in blockers] == ["discount_rate_unavailable"]
    model["eligibility"]["missing_inputs"] = ["shares"]
    assert model_blockers({"annual_periods": [{}], "basis": {"share_basis_verified": True}}, model)[0]["code"] == "required_metric_missing"


def test_manual_comparison_and_currency_gate_do_not_destroy_independent_proofs():
    from datetime import UTC, datetime
    inputs = retained_inputs()["MSFT"]
    inputs["market"] = {"price": 100, "price_timestamp": "2026-10-20T11:00:00Z", "currency": "USD", "status": "fresh"}
    inputs["basis"]["share_basis_verified"] = True
    inputs["company"].update(instrument_id="fixture", security_form="adr", identity_status="verified", adr_metadata={})
    result = compatibility(inputs, {"source_type": "user", "status": "user_provided", "provider_currency": "USD"}, datetime(2026, 10, 20, 12, tzinfo=UTC))
    assert result["market_price"]["status"] == "available"
    assert result["share_basis"]["status"] == "available"


def test_candidate_input_provenance_includes_direct_reported_facts():
    inputs = retained_inputs()["MSFT"]
    result = enrich_valuation_coverage(inputs, calculate_valuation(inputs))
    model = next(row for row in result["financial_coverage"]["models"] if row["id"] == "evRevenue")
    record = model["candidate_input_sources"]["revenue"]
    assert record["value"] == inputs["values"]["revenue"]
    assert record["provenance"] == inputs["facts"]["revenue"]["provenance"]
    assert record["reported_record"]["value"] == inputs["facts"]["revenue"]["value"]
