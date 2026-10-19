"""Audits never turn directory coverage or synthetic fixtures into valuations."""
from copy import deepcopy
import json

import pytest

from app.registry.audit import summarize, markdown_matrix
from app.services.coverage_service import stage
from app.services.coverage_service import failure_stage
from app.services.coverage_service import CoverageService
from app.schemas.coverage import CoverageStages
from app.providers.base import ProviderError
from coverage_sample_helpers import FIXTURES, replay_reference_sample


def bundle():
    return {"data_mode": "mocked", "as_of": "2026-10-18T12:00:00Z", "samples": [{
        "requested_symbol": "SYN", "data_mode": "mocked", "sector": "Synthetic",
        "coverage": {"identity": {"ticker": "SYN", "instrument_id": "synthetic-a", "issuer_id": "synthetic-issuer", "exchange": "TEST", "instrument_type": "common_stock"},
            "as_of": "2026-10-18T11:00:00Z", "methodology_version": "synthetic-1",
            "stages": {name: stage("missing_evidence", "Synthetic missing stage.") for name in
                       ("symbol_resolution", "classification", "profile", "statements", "normalization", "freshness", "valuation", "ai_research")}}}]}


def test_sample_audit_preserves_missing_counts_status_and_denominators():
    source = bundle()
    result = summarize(source)
    assert result["sample_denominator"] == 1
    assert result["unique_issuer_denominator"] == 1
    assert result["samples"][0]["contributing_model_count"] is None
    assert result["samples"][0]["ai_evidence_available"] is None
    assert result["samples"][0]["generated_report"] == "not_audited"
    assert result["groups"]["exchange"]["TEST"]["sample_denominator"] == 1
    assert source == bundle()
    assert result["samples"][0]["valuation_quality"] is None
    assert len(result["samples"][0]["unresolved_blockers"]) == len(CoverageStages.model_fields)


def test_audit_matrix_preserves_exact_quality_counts_and_scoped_restrictions():
    source = bundle()
    stages = source["samples"][0]["coverage"]["stages"]
    stages["profile"] = stage("available", "A sourced identity profile is retained.", provider_restrictions=["provider_subscription_required"])
    stages["valuation"].update(contributing_model_count=0, eligible_models=[], quality="low", confidence="low")
    result = summarize(source)
    row = result["samples"][0]
    assert row["valuation_quality"] == row["valuation_confidence"] == "low"
    assert row["provider_restrictions"] == [{"stage": "profile", "codes": ["provider_subscription_required"]}]
    rendered = markdown_matrix(result)
    for column in ("Resolution", "Profile", "Statements", "Contributing models", "Quality", "Provider restrictions", "Unresolved blockers"):
        assert column in rendered
    assert "profile: provider_subscription_required" in rendered
    assert "None eligible | 0 | low" in rendered
    assert source["samples"][0]["coverage"]["stages"]["valuation"]["contributing_model_count"] == 0


def test_audit_markdown_escapes_source_text_without_changing_saved_json():
    source = bundle()
    source["samples"][0]["requested_symbol"] = "SYN|<tag>"
    source["samples"][0]["coverage"]["stages"]["valuation"]["reason"] = "A source|reason\n<script>"
    result = summarize(source)
    rendered = markdown_matrix(result)
    assert "SYN&#124;&lt;TAG&gt;" in rendered
    assert "&lt;script&gt;" in rendered and "<script>" not in rendered
    assert result["samples"][0]["requested_symbol"] == "SYN|<TAG>"
    assert source["samples"][0]["coverage"]["stages"]["valuation"]["reason"] == "A source|reason\n<script>"


@pytest.mark.parametrize("code", ["cache_refresh_busy", "cache_lease_lost"])
def test_cache_coordination_failure_is_temporary_not_missing_financial_evidence(code):
    result = failure_stage(ProviderError(code, "A bounded refresh is temporarily unavailable.", 503, True))
    assert result["status"] == "temporarily_unavailable"
    assert result["reason_codes"] == [code]


@pytest.mark.asyncio
@pytest.mark.parametrize("financial_code,market_code,expected", [("not_found", "provider_subscription_required", "missing_evidence"),
    ("provider_timeout", "provider_access_denied", "temporarily_unavailable"),
    ("provider_access_denied", "not_found", "provider_restricted")])
async def test_financial_coverage_uses_financial_source_failures_independently(financial_code, market_code, expected):
    company = {"ticker": "SYN", "cik": "0000000001", "issuer_id": "synthetic-issuer", "instrument_id": "synthetic-instrument",
               "listing_id": "synthetic-listing", "instrument_type": "common_stock", "identity_status": "verified", "listing_status": "active"}
    class Companies:
        async def company_identity(self, *_args, **_scope):
            return company, None
    class Valuations:
        async def inputs(self, *_args, **_scope):
            return {"company": company, "facts": {}, "annual_periods": [], "warnings": [
                {"field": "market_price", "code": market_code}],
                "financial_source_status": {"status": "unavailable", "error_code": financial_code, "warnings": []}}
        async def calculate(self, *_args, **_scope):
            return {"scenarios": {"base": {"summary": {"count": 0}, "models": []}}}
    result = await CoverageService(Companies(), None, Valuations()).coverage("SYN")
    for name in ("statements", "valuation"):
        assert result["stages"][name]["status"] == expected
        assert result["stages"][name]["reason_codes"] == [financial_code]
    assert result["stages"]["profile"]["status"] == "missing_evidence"


@pytest.mark.parametrize("mutation", ["mixed_modes", "duplicate", "naive_clock", "future_observation", "invented_status", "missing_stage", "fractional_count", "negative_count", "too_many_models", "credential"])
def test_invalid_or_misleading_audits_are_rejected(mutation):
    source = bundle()
    if mutation == "mixed_modes": source["samples"][0]["data_mode"] = "retained_public"
    elif mutation == "duplicate": source["samples"].append(deepcopy(source["samples"][0]))
    elif mutation == "naive_clock": source["as_of"] = "2026-10-18T12:00:00"
    elif mutation == "future_observation": source["samples"][0]["coverage"]["as_of"] = "2026-10-19T12:00:00Z"
    elif mutation == "invented_status": source["samples"][0]["coverage"]["stages"]["valuation"]["status"] = "universal"
    elif mutation == "missing_stage": del source["samples"][0]["coverage"]["stages"]["freshness"]
    elif mutation == "credential": source["api_key"] = "forbidden"
    else: source["samples"][0]["coverage"]["stages"]["valuation"]["contributing_model_count"] = {"fractional_count": 1.5, "negative_count": -1, "too_many_models": 12}[mutation]
    with pytest.raises((ValueError, KeyError)):
        summarize(source)


def test_retained_reference_fixture_has_exact_registered_issuer_mappings():
    data = json.loads((FIXTURES / "sec_reference_sample_2026_10_18.json").read_text(encoding="utf-8"))
    assert len(data["samples"]) == 25
    assert data["directory_record_count"] == 10444
    for sample in data["samples"]:
        assert len(sample["directory_records"]) == 1
        record = sample["directory_records"][0]
        assert record["instrument_type"] == "unknown"
        assert record["listing_status"] == "unknown"
        assert record["identity_status"] == "reference_only"
        if sample["submissions"]:
            assert str(sample["submissions"]["cik"]).zfill(10) == record["cik"]
            assert record["ticker"] in sample["submissions"]["tickers"]
    assert "addresses" not in json.dumps(data)


@pytest.mark.asyncio
async def test_real_reference_sample_is_separate_from_financial_and_valuation_coverage(session_factory):
    result = summarize(await replay_reference_sample(session_factory))
    assert result["sample_denominator"] == 25
    assert result["unique_issuer_denominator"] == 24  # GOOG/GOOGL share the verified CIK.
    assert result["stage_status_counts"]["symbol_resolution"] == {"available": 25}
    assert result["stage_status_counts"]["statements"].get("available") == 5
    assert result["stage_status_counts"]["valuation"] == {"missing_evidence": 25}
    assert all(row["contributing_model_count"] == 0 for row in result["samples"])
    assert all(row["generated_report"] == "not_audited" for row in result["samples"])
    jpm = next(row for row in result["samples"] if row["requested_symbol"] == "JPM")
    assert jpm["stages"]["statements"]["reporting_period"]["end_date"] == "2025-12-31"
    assert jpm["ai_evidence_available"] is True
