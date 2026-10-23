"""Real SEC dividend scenario retains strict dates, identity and publication."""
from copy import deepcopy
from datetime import datetime
import json
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from fastapi import FastAPI

from app.api.routes.valuation import router
from app.core.config import Settings
from app.core.exceptions import ApiError
from app.repositories.financial_repository import FinancialRepository
from app.services.financial_import_service import apply_preview, build_preview
from app.services.normalization import normalize_company_facts
from app.services.valuation_service import ValuationService
from app.valuation.coverage import calculate_with_coverage, enrich_valuation_coverage
from app.valuation.dated_intrinsic import prepare_dated_intrinsic
from app.valuation.engine import calculate_valuation
from app.valuation.schemas import ValuationRequest, ValuationResponse
from phase68_valuation_helpers import import_registry, real_fixture, real_inputs, request, retain_profile
from test_phase68_financial_import import retained_source


def test_exact_real_msft_common_dividend_scenario(session_factory):
    inputs = real_inputs(session_factory)
    original = deepcopy(inputs)
    result = calculate_with_coverage(inputs, request())
    base = result["scenarios"]["base"]
    assert base["summary"]["fair_value"] == pytest.approx(53.56)
    assert base["summary"]["classification"] == "user_defined"
    assert base["summary"]["count"] == 1
    assert base["publication"]["result_type"] == "historical_illustration"
    assert base["publication"]["current_eligible"] is False
    assert base["market_comparison"]["status"] == "unavailable"
    assert base["market_comparison"]["price"] is None and base["market_comparison"]["upside"] is None
    intrinsic = base["intrinsic"]
    assert intrinsic["financial_observation_date"] == "2026-06-30"
    assert intrinsic["forecast_horizon"]["first_forecast_start"] == "2026-07-01"
    assert intrinsic["forecast_horizon"]["first_forecast_end"] == "2027-06-30"
    assert intrinsic["source_identifiers"] == ["0001193125-26-323660"]
    assert intrinsic["source_facts"]["declared_common_dividend_per_share"]["value"] == 3.64
    assert intrinsic["assumptions"]["dividend_per_share"]["evidence_type"] == "fact"
    assert intrinsic["assumptions"]["cost_of_equity"]["evidence_type"] == "user"
    assert result["reverse_dcf"]["status"] == "unavailable"
    assert ValuationResponse.model_validate(result).scenarios["base"].intrinsic["value"] == pytest.approx(53.56)
    assert inputs == original


def test_default_stays_blocked_and_missing_sustainability_never_invented(session_factory):
    inputs = real_inputs(session_factory)
    result = calculate_with_coverage(inputs)
    assert result["scenarios"]["base"]["summary"]["fair_value"] is None
    dividend = next(model for model in result["scenarios"]["base"]["models"] if model["id"] == "dividend")
    assert "stable_dividend_confirmed" in dividend["eligibility"]["missing_inputs"]
    assert result["financial_coverage"]["publication"]["current_eligible"] is False


def installed_old_registry_with_archived_attachment(session_factory):
    """Simulate the installed 19-Oct proof shape; financial values stay real."""
    inputs = real_inputs(session_factory)
    company = inputs["company"]
    fields = ("issuer_id", "instrument_id", "listing_id", "cik", "ticker", "exchange_mic", "security_form", "listing_status",
              "listing_verification", "issuer_linkage", "proof_expiry")
    attachment = {field: deepcopy(company[field]) for field in fields}
    attachment.update(package_hash="a" * 64, source_inventory=[{"kind": "nasdaqlisted"}, {"kind": "company_tickers_exchange"}])
    for kind in ("listing", "issuer_linkage"):
        company["proof_expiry"][kind].update(observed_on="2026-10-19", expires_at="2026-10-20T00:00:00Z", state="verification_expired")
    company["listing_verification"]["observed_on"] = "2026-10-19"
    company["issuer_linkage"].pop("retrieved_at", None)
    inputs["archived_identity_evidence"] = attachment
    return inputs


def test_approved_archived_attachment_supports_dated_value_without_refreshing_installed_registry(session_factory):
    inputs = installed_old_registry_with_archived_attachment(session_factory)
    original = deepcopy(inputs)
    result = calculate_with_coverage(inputs, request())
    base = result["scenarios"]["base"]
    assert base["intrinsic"]["value"] == pytest.approx(53.56)
    assert base["intrinsic"]["evidence_context"]["identity_proof_origin"] == "approved_archived_reference_attachment"
    assert base["publication"]["clocks"]["listing"]["observed_on"] == "2026-10-19"
    assert not base["publication"]["current_eligible"]
    assert inputs == original


@pytest.mark.parametrize("field,value", [("listing_id", "wrong-listing"), ("cik", "0000320193"), ("exchange_mic", "XNYS"), ("ticker", "GOOGL")])
def test_archived_attachment_cannot_transfer_to_a_different_security(session_factory, field, value):
    inputs = installed_old_registry_with_archived_attachment(session_factory)
    inputs["archived_identity_evidence"][field] = value
    with pytest.raises(ApiError, match="exact selected security"):
        prepare_dated_intrinsic(inputs, request())


@pytest.mark.parametrize("mutation", ["unknown_id", "wrong_cik", "wrong_venue", "conflicting", "ineligible_class", "missing_hash", "forged_expiry", "future_retrieval", "wrong_profile", "future_filing", "source_precedes_filing"])
def test_dated_context_rejects_invalid_scope_and_sources(session_factory, mutation):
    inputs = real_inputs(session_factory)
    company = inputs["company"]
    if mutation == "unknown_id": company["instrument_id"] = None
    elif mutation == "wrong_cik": company["issuer_linkage"]["cik"] = "0000320193"
    elif mutation == "wrong_venue": company["issuer_linkage"]["exchange_mic"] = "XNYS"
    elif mutation == "conflicting": company["listing_verification"]["conflicts"] = [{"field": "security_form"}]
    elif mutation == "ineligible_class": company["security_form"] = "preferred"
    elif mutation == "missing_hash": company["listing_verification"]["record_hash"] = None
    elif mutation == "forged_expiry": company["proof_expiry"]["listing"]["expires_at"] = "2027-10-22T00:00:00Z"
    elif mutation == "future_retrieval": company["listing_verification"]["retrieved_at"] = "2027-10-22T00:00:00Z"
    elif mutation == "wrong_profile": inputs["dated_share_basis_evidence"]["cik"] = "0000320193"
    elif mutation == "future_filing": inputs["facts"]["declared_common_dividend_per_share"]["provenance"][0]["filed"] = "2027-01-01"
    elif mutation == "source_precedes_filing": inputs["financial_retrieved_at"] = "2026-07-01T00:00:00Z"
    with pytest.raises(ApiError):
        prepare_dated_intrinsic(inputs, request())


@pytest.mark.parametrize("as_of", ["2026-10-21T00:01:00Z", "2026-10-22T00:00:00Z", "2026-10-23T00:00:00Z", "2027-01-01T00:00:00Z"])
def test_dated_clock_never_renews_expired_or_unacquired_evidence(session_factory, as_of):
    with pytest.raises(ApiError):
        prepare_dated_intrinsic(real_inputs(session_factory), request(evidence_as_of=as_of), clock="2026-10-22T06:51:30Z")


@pytest.mark.parametrize("edits", [{"manual_market_price": {"value": 100.0, "currency": "USD"}}, {"enabled_models": ["pe"]},
    {"assumptions": {"dividend_growth": 0.03, "cost_of_equity": 0.10, "stable_dividend_confirmed": True, "dividend_per_share": 99}},
    {"assumptions": {"dividend_growth": 0.03, "cost_of_equity": 0.10, "stable_dividend_confirmed": False}}])
def test_dated_request_rejects_current_comparison_and_financial_overrides(session_factory, edits):
    with pytest.raises(ApiError, match="dated intrinsic workflow"):
        prepare_dated_intrinsic(real_inputs(session_factory), request(**edits))


@pytest.mark.parametrize("unit,concept,value,start", [("USD", "CommonStockDividendsPerShareDeclared", 3.64, "2025-07-01"),
    ("USD/shares", "PaymentsOfDividendsCommonStock", 3.64, "2025-07-01"),
    ("USD/shares", "CommonStockDividendsPerShareDeclared", 3.64, "2026-04-01"),
    ("USD/shares", "CommonStockDividendsPerShareDeclared", -3.64, "2025-07-01")])
def test_dividend_disclosure_never_substitutes_issuer_totals_wrong_periods_or_units(unit, concept, value, start):
    raw = real_fixture()["raw"]
    definition = raw["facts"]["us-gaap"].pop("CommonStockDividendsPerShareDeclared")
    row = deepcopy(definition["units"]["USD/shares"][-1])
    row.update(start=start, val=value)
    raw["facts"]["us-gaap"][concept] = {"units": {unit: [row]}}
    normalized = normalize_company_facts(raw, cik="0000789019")
    assert not normalized["reviewed_disclosures"]["annual_common_dividends"]


def test_disclosure_conflicting_exact_latest_filing_is_quarantined():
    raw = real_fixture()["raw"]
    rows = raw["facts"]["us-gaap"]["CommonStockDividendsPerShareDeclared"]["units"]["USD/shares"]
    duplicate = deepcopy(rows[-1]); duplicate["val"] += 1
    rows.append(duplicate)
    normalized = normalize_company_facts(raw, cik="0000789019")
    assert not any(row["period"]["end_date"] == "2026-06-30" for row in normalized["reviewed_disclosures"]["annual_common_dividends"])


@pytest.mark.asyncio
@pytest.mark.parametrize("archived", [False, True])
async def test_imported_real_sec_facts_reach_normal_api_without_provider_calls(engine, session_factory, tmp_path, archived):
    fixture = real_fixture()
    registry = import_registry(session_factory)
    retain_profile(session_factory)
    attachment = None
    if archived:
        from app.models.security_registry import SecurityListing
        from test_phase68_archived_security_import import archive_spec
        identity = registry.repository.resolve("MSFT")
        with session_factory.begin() as session:
            listing = session.get(SecurityListing, identity["listing_id"])
            old = deepcopy(listing.verification)
            old.update(observed_on="2026-10-19", retrieved_at="2026-10-19T11:45:39Z")
            old["issuer_linkage"].update(observed_on="2026-10-19", retrieved_at=None)
            listing.verification = old
        attachment = archive_spec(tmp_path, identity)
    spec = retained_source(tmp_path, fixture["raw"], ticker="MSFT")
    plan = build_preview(engine, [spec], as_of=fixture["audit_clock"], sec_cache_ttl_seconds=21600,
                         archived_security_package=attachment)
    apply_preview(engine, plan, confirmation=f"APPLY {plan['preview_digest']}")
    async def forbidden(*_args, **_kwargs):
        pytest.fail("Dated API must not invoke company, financial provider or ordinary snapshot loaders.")
    companies = SimpleNamespace(registry=registry, profile=forbidden, company_identity=forbidden)
    financials = SimpleNamespace(repository=FinancialRepository(session_factory), dataset=forbidden)
    service = ValuationService(companies, financials, Settings())
    application = FastAPI(); application.include_router(router, prefix="/api")
    application.state.valuation_service = service
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://local") as client:
        response = await client.post("/api/stocks/MSFT/valuation/calculate", json=request().model_dump(mode="json"))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["scenarios"]["base"]["intrinsic"]["value"] == pytest.approx(53.56)
    assert result["scenarios"]["base"]["intrinsic"]["workflow"] == "user_assisted"
    assert result["scenarios"]["base"]["market_comparison"]["upside"] is None
    assert result["financial_coverage"]["publication"]["current_eligible"] is False
    assert len(result["scenarios"]["base"]["models"]) == 11
    if archived:
        assert result["scenarios"]["base"]["intrinsic"]["evidence_context"]["identity_proof_origin"] == "approved_archived_reference_attachment"
        assert result["scenarios"]["base"]["publication"]["clocks"]["listing"]["observed_on"] == "2026-10-19"
