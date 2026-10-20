"""Synthetic financial examples test architecture, not actual issuer coverage."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select

from app.core.exceptions import ApiError
from app.models import Company, FinancialFact, SecurityIssuer
from app.providers.base import ProviderError
from app.providers.market_data import FmpMarketDataProvider
from app.providers.sec_edgar import SecEdgarProvider
from app.repositories.financial_repository import FinancialRepository
from app.services.security_identity import applicability, cache_scope, check_provider_identity, same_identity
from app.valuation.eligibility import eligibility
from app.valuation.schemas import MODEL_IDS
from test_api import client  # Isolated SQLite app and mocked providers only.


def synthetic_identity(**changes):
    return {"ticker": "SYN", "name": "Explicitly synthetic identity example", "cik": "0000000001",
            "issuer_id": "issuer-test-1", "instrument_id": "instrument-test-1", "listing_id": "listing-test-1",
            "exchange": "NASDAQ", "exchange_mic": "XNAS", "instrument_type": "common_stock",
            "listing_status": "active", "identity_status": "verified", "aliases": [],
            "provider_symbols": {}, "has_multiple_share_classes": False, "sic": "3571",
            "source_refs": [{"provider": "synthetic-fixture", "scope": "No real company financial coverage claim."}], **changes}


class Registry:
    def __init__(self, identity):
        self.identity = identity

    async def resolve(self, ticker, instrument_id=None, listing_id=None):
        if (instrument_id and instrument_id != self.identity["instrument_id"]) or (listing_id and listing_id != self.identity["listing_id"]):
            raise ApiError("identity_ambiguous", "The requested instrument does not match.", 409)
        return deepcopy(self.identity)


def attach(client, **changes):
    company = synthetic_identity(**changes)
    if company.get("cik"):
        with client.app.state.session_factory.begin() as session:
            if session.get(SecurityIssuer, company["issuer_id"]) is None:
                session.add(SecurityIssuer(id=company["issuer_id"], source_key="synthetic:" + company["issuer_id"],
                    cik=company["cik"], name=company["name"], source_refs=[]))
    client.app.state.company_service.registry = Registry(company)
    return company


def test_cache_scope_separates_classes_listings_and_issuer_reassignment():
    base = synthetic_identity()
    scopes = {cache_scope(base)}
    for changes in ({"instrument_id": "class-b"}, {"issuer_id": "new-issuer", "cik": "0000000002"},
                    {"listing_id": "new-listing"}, {"exchange_mic": "XNYS"}):
        scopes.add(cache_scope({**base, **changes}))
    assert len(scopes) == 5
    assert cache_scope({"ticker": "SYN"}) == "SYN"
    assert not same_identity(base, {**base, "instrument_id": "class-b"})
    assert not same_identity(base, {key: value for key, value in base.items() if key != "instrument_id"})


@pytest.mark.parametrize("kind", ["etf", "closed_end_fund", "preferred", "warrant", "right", "unit", "other"])
@pytest.mark.parametrize("model_id", MODEL_IDS)
def test_unsupported_instruments_cannot_be_enabled_by_manual_assumptions(kind, model_id):
    company = synthetic_identity(instrument_type=kind)
    result = eligibility(model_id, {"company": company, "currency": "USD", "basis": {}},
                         {"forward_eps": 10, "target_pe": 20, "share_basis_confirmed": True, "is_bank": False,
                          "is_reit": False, "affo_basis_confirmed": True}, overridden={"forward_eps"})
    assert result["status"] == "ineligible"
    assert "unsupported_instrument_type" in result["reason_codes"]


@pytest.mark.parametrize("kind", ["unknown", None])
def test_unclassified_registry_instrument_is_unavailable_not_assumed_common_stock(kind):
    company = synthetic_identity(instrument_type=kind)
    result = eligibility("pe", {"company": company, "currency": "USD"},
                         {"forward_eps": 10, "target_pe": 20, "share_basis_confirmed": True}, overridden={"forward_eps"})
    assert result["status"] == "unavailable"
    assert "instrument_classification_unverified" in result["reason_codes"]


@pytest.mark.parametrize("kind", ["financial_institution", "insurance"])
def test_financial_institution_enterprise_gate_is_not_overridden(kind):
    result = eligibility("fcff", {"company": synthetic_identity(instrument_type=kind), "currency": "USD"},
                         {"is_bank": False, "is_reit": False, "share_basis_confirmed": True})
    assert result["status"] == "ineligible"
    assert "financial_institution_enterprise_framework" in result["reason_codes"]


def test_registry_reit_cannot_be_reclassified_by_editor_flag():
    result = eligibility("pe", {"company": synthetic_identity(instrument_type="reit"), "currency": "USD"},
                         {"is_reit": False, "forward_eps": 10, "target_pe": 20, "share_basis_confirmed": True})
    assert result["status"] == "ineligible"
    assert "reit_gaap_earnings_not_cash_earnings" in result["reason_codes"]


@pytest.mark.parametrize("ratio", [None, 0, -1, True, float("inf")])
def test_adr_ratio_must_be_finite_positive_verified_and_security_compatible(ratio):
    company = synthetic_identity(instrument_type="adr", adr_metadata={"ratio": ratio, "ratio_verified": True,
        "share_basis_verified": True, "reporting_currency": "USD", "quote_currency": "USD"})
    assert applicability(company)[0] == "adr_share_basis_unverified"


def test_foreign_quote_currency_mismatch_cannot_be_replaced_by_user_forecast():
    company = synthetic_identity(instrument_type="foreign_ordinary", share_basis_verified=True,
                                 reporting_currency="EUR", quote_currency="USD")
    result = eligibility("pe", {"company": company, "currency": "USD"},
                         {"forward_eps": 10, "target_pe": 20, "share_basis_confirmed": True}, overridden={"forward_eps"})
    assert result["status"] == "unavailable"
    assert "foreign_currency_basis_unverified" in result["reason_codes"]


@pytest.mark.parametrize("payload", [{"cik": "2"}, {"ticker": "OTHER"}, {"exchange": "NYSE"}, {"share_class": "Class B"},
                                     {"isEtf": True}, {"isFund": True}, {"isAdr": True}])
def test_provider_identity_mismatches_fail_closed(payload):
    with pytest.raises(ApiError):
        check_provider_identity(synthetic_identity(share_class="Class A"), payload)


def test_only_explicit_provider_alias_is_accepted():
    identity = synthetic_identity(ticker="BRK.B", symbol_aliases=["BRK-B"], provider_symbols={"fmp": "BRK-B"})
    check_provider_identity(identity, {"symbol": "BRK-B", "exchange": "XNAS", "cik": "1"})
    with pytest.raises(ApiError):
        check_provider_identity({**identity, "symbol_aliases": [], "provider_symbols": {}}, {"symbol": "BRK-B"})
    with pytest.raises(ApiError):
        check_provider_identity(synthetic_identity(aliases=["OTHER"]), {"symbol": "OTHER"})


def test_repository_preserves_historical_issuer_on_symbol_reuse(session_factory):
    repo = FinancialRepository(session_factory)
    original = synthetic_identity()
    with session_factory.begin() as session:
        session.add(SecurityIssuer(id=original["issuer_id"], source_key="synthetic:original", cik=original["cik"], name=original["name"], source_refs=[]))
    company_id = repo.save_company(original)
    with pytest.raises(ApiError, match="historical data"):
        repo.save_company({**original, "cik": "0000000002", "issuer_id": "issuer-reused"})
    with session_factory() as session:
        assert session.get(Company, company_id).cik == "0000000001"


def test_outside_four_synthetic_company_gets_scoped_dashboard_and_model_reasons(client):
    identity = attach(client)
    query = "?instrument_id=" + identity["instrument_id"]
    profile = client.get("/api/stocks/SYN" + query)
    assert profile.status_code == 200
    assert profile.json()["company"]["instrument_id"] == identity["instrument_id"]
    statements = client.get("/api/stocks/SYN/financials" + query).json()
    assert statements["identity"]["issuer_id"] == identity["issuer_id"]
    assert statements["periods"]
    result = client.get("/api/stocks/SYN/valuation/defaults" + query)
    assert result.status_code == 200
    assert len(result.json()["scenarios"]["base"]["models"]) == 11
    coverage = client.get("/api/stocks/SYN/coverage" + query).json()
    assert coverage["stages"]["symbol_resolution"]["status"] == "available"
    assert coverage["stages"]["statements"]["status"] == "available"
    assert coverage["stages"]["ai_research"]["evidence_available"] is True


def test_registry_unknown_type_keeps_financials_but_blocks_all_valuation_models(client):
    attach(client, instrument_type="unknown")
    assert client.get("/api/stocks/SYN/financials").status_code == 200
    result = client.post("/api/stocks/SYN/valuation/calculate", json={"assumptions": {"forward_eps": 10, "target_pe": 20}}).json()
    assert result["scenarios"]["base"]["summary"]["count"] == 0
    assert all(row["fair_value"] is None for row in result["scenarios"]["base"]["models"])
    coverage = client.get("/api/stocks/SYN/coverage").json()
    assert coverage["stages"]["classification"]["status"] == "missing_evidence"
    assert coverage["stages"]["statements"]["status"] == "available"


def test_unsupported_etf_keeps_profile_but_never_fetches_issuer_facts(client, fake_providers):
    attach(client, instrument_type="etf")
    assert client.get("/api/stocks/SYN").status_code == 200
    result = client.get("/api/stocks/SYN/valuation/defaults").json()
    assert result["scenarios"]["base"]["summary"]["count"] == 0
    assert fake_providers[0].facts_calls == 0
    coverage = client.get("/api/stocks/SYN/coverage").json()
    assert coverage["stages"]["valuation"]["status"] == "financially_inapplicable"
    assert coverage["stages"]["classification"]["status"] == "available"
    assert coverage["stages"]["classification"]["supported_operating_company_valuation"] is False


def test_missing_cik_is_profile_only_without_invented_financials(client, fake_providers):
    attach(client, cik=None)
    assert client.get("/api/stocks/SYN").status_code == 200
    assert client.get("/api/stocks/SYN/financials").json()["error"]["code"] == "missing_cik"
    valuation = client.get("/api/stocks/SYN/valuation/defaults").json()
    assert valuation["currency"] is None
    assert valuation["scenarios"]["base"]["summary"]["fair_value"] is None
    assert fake_providers[0].facts_calls == 0


def test_stable_identity_does_not_read_legacy_symbol_quote_cache(client):
    service = client.app.state.company_service
    service.cache._write("market:fixture-market:quote:SYN", {"price": 999, "currency": "USD"}, 3600, "fixture-market")
    identity = attach(client)
    result = client.get("/api/stocks/SYN").json()
    assert result["market"]["price"] == 100
    assert service.cache._read(f"market:fixture-market:quote:{cache_scope(result['company'])}") is not None
    assert service.cache._read("market:fixture-market:quote:SYN").payload["price"] == 999


def test_concurrent_company_analysis_fetches_shared_sources_once(client, fake_providers):
    identity = attach(client)
    path = "/api/stocks/SYN/valuation/defaults?instrument_id=" + identity["instrument_id"]
    with ThreadPoolExecutor(max_workers=5) as pool:
        responses = list(pool.map(lambda _: client.get(path), range(5)))
    assert all(response.status_code == 200 for response in responses)
    assert fake_providers[0].facts_calls == 1
    assert fake_providers[1].quote_calls == 1
    assert len(client.app.state.valuation_service._snapshots) == 1


@pytest.mark.parametrize("changes,reason", [({"identity_status": "reference_only"}, "security_identity_unverified"),
                                           ({"listing_status": "unknown"}, "listing_status_unverified"),
                                           ({"listing_status": "delisted"}, "inactive_listing")])
def test_reference_identity_or_listing_status_does_not_establish_valuation_eligibility(changes, reason):
    assert applicability(synthetic_identity(**changes))[0] == reason


def test_nonunit_adr_ratio_is_not_silently_applied_to_issuer_financials():
    company = synthetic_identity(instrument_type="adr", adr_metadata={"ratio": 5, "ratio_verified": True,
        "share_basis_verified": True, "reporting_currency": "USD", "quote_currency": "USD"})
    assert applicability(company)[0] == "adr_per_security_conversion_unsupported"


def test_ifrs_only_source_retains_raw_observations_without_asserting_usd_statements(client, fake_providers):
    attach(client, instrument_type="foreign_ordinary")
    fake_providers[0].raw_facts = {"cik": 1, "facts": {"ifrs-full": {"Revenue": {"units": {"EUR": [
        {"val": 120, "start": "2024-01-01", "end": "2024-12-31", "fy": 2024, "fp": "FY",
         "form": "20-F", "filed": "2025-03-01", "accn": "synthetic-ifrs-observation"}]}}}}}
    result = client.get("/api/stocks/SYN/financials").json()
    assert result["currency"] is None
    assert result["periods"] == []
    assert any(row["code"] == "unsupported_ifrs_normalization" for row in result["warnings"])


def test_provider_cik_conflict_does_not_publish_enrichment_or_financials(client, fake_providers):
    attach(client)
    async def mismatch(_ticker):
        return {"cik": "0000000002", "description": "Wrong company"}
    fake_providers[1].profile = mismatch
    response = client.get("/api/stocks/SYN")
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "incompatible_financial_identity"


def test_registered_reused_symbol_preserves_both_financial_owners(client, session_factory):
    attach(client)
    assert client.get("/api/stocks/SYN/financials").status_code == 200
    attach(client, cik="0000000002", issuer_id="issuer-reused", instrument_id="instrument-reused", listing_id="listing-reused")
    profile = client.get("/api/stocks/SYN").json()
    assert profile["company"]["cik"] == "0000000002"
    assert not any(row["code"] == "incompatible_financial_identity" for row in profile["warnings"])
    response = client.get("/api/stocks/SYN/financials")
    assert response.status_code == 502  # Fixture facts still belong to the old CIK.
    with session_factory() as session:
        company = session.scalar(select(Company).where(Company.ticker == "SYN", Company.cik == "0000000001"))
        assert company.cik == "0000000001"
        assert session.scalar(select(FinancialFact).where(FinancialFact.company_id == company.id)) is not None


@pytest.mark.parametrize("path,method", [("", "get"), ("/resolve", "get"), ("/coverage", "get"),
    ("/financials", "get"), ("/metrics", "get"), ("/data-status", "get"), ("/prices", "get"),
    ("/valuation/defaults", "get"), ("/valuation/eligibility", "get"), ("/valuation/explain", "get"),
    ("/valuation/calculate", "post"), ("/valuation/scenarios", "post")])
def test_all_analysis_routes_preserve_explicit_listing_selection(client, path, method):
    with client.app.state.session_factory.begin() as session:
        session.add(SecurityIssuer(id="issuer-test-1", source_key="synthetic:route-scope", cik="0000000001", name="Synthetic", source_refs=[]))
    class Listings:
        async def resolve(self, _ticker, instrument_id=None, listing_id=None):
            if listing_id not in {"listing-first", "listing-second"}:
                raise ApiError("identity_ambiguous", "Choose a listing.", 409)
            if instrument_id is not None and instrument_id != "instrument-test-1":
                raise ApiError("identity_ambiguous", "Wrong instrument.", 409)
            return synthetic_identity(listing_id=listing_id)
    client.app.state.company_service.registry = Listings()
    url = "/api/stocks/SYN" + path
    request = getattr(client, method)
    options = {"json": {}} if method == "post" else {}
    assert request(url, params={"instrument_id": "instrument-test-1"}, **options).status_code in {200, 409}
    for listing in ("listing-first", "listing-second"):
        response = request(url, params={"instrument_id": "instrument-test-1", "listing_id": listing}, **options)
        assert response.status_code == 200, response.text
        body = response.json()
        identity = body.get("company", body.get("identity"))
        assert identity["listing_id"] == listing


def test_missing_cik_in_scoped_sec_facts_is_not_persisted_or_cached_as_verified(client, fake_providers, session_factory):
    attach(client)
    fake_providers[0].raw_facts.pop("cik")
    result = client.get("/api/stocks/SYN/financials")
    assert result.status_code == 502
    assert result.json()["error"]["code"] == "incompatible_financial_identity"
    assert client.app.state.company_service.cache._read("sec:facts:0000000001") is None
    with session_factory() as session:
        assert session.scalar(select(FinancialFact)) is None


def test_registry_freshness_is_not_replaced_by_fresh_financial_or_quote_retrieval(client):
    original = "2026-10-18T00:00:00+00:00"
    attach(client, registry_as_of="2020-01-01", registry_retrieved_at=original, registry_status="stale",
           registry_warnings=[{"field": "security_registry", "code": "stale_registry_reference", "message": "Synthetic dated reference."}])
    profile = client.get("/api/stocks/SYN").json()
    assert profile["company"]["registry_retrieved_at"] == original
    assert profile["company"]["registry_as_of"] == "2020-01-01"
    assert profile["status"] == "stale"
    coverage = client.get("/api/stocks/SYN/coverage").json()
    assert coverage["stages"]["statements"]["status"] == "available"
    assert coverage["stages"]["freshness"]["status"] == "missing_evidence"
    assert coverage["stages"]["freshness"]["registry_status"] == "stale"
    assert coverage["stages"]["freshness"]["registry_retrieved_at"] == original


@pytest.mark.asyncio
async def test_scoped_sec_submissions_require_an_explicit_matching_cik():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"name": "Synthetic", "tickers": ["SYN"]}))) as client:
        sec = SecEdgarProvider(client, user_agent="Fixture fixture@example.invalid", min_interval=0, retries=0)
        with pytest.raises(ProviderError) as error:
            await sec.company_for_identity(synthetic_identity())
        assert error.value.code == "incompatible_financial_identity"


@pytest.mark.asyncio
async def test_sec_submissions_cik_conflict_and_identity_enrichment_use_exact_issuer():
    seen = []
    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(200, json={"cik": "2", "name": "Wrong issuer"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        sec = SecEdgarProvider(client, user_agent="Fixture fixture@example.invalid", min_interval=0, retries=0)
        with pytest.raises(ProviderError) as error:
            await sec.company_for_identity(synthetic_identity())
    assert error.value.code == "incompatible_financial_identity"
    assert seen == ["/submissions/CIK0000000001.json"]


@pytest.mark.asyncio
async def test_fmp_profile_internal_cache_isolated_on_ticker_reassignment():
    calls = []
    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json=[{"symbol": "SYN", "companyName": "Synthetic", "cik": str(len(calls)), "exchange": "NASDAQ"}])
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = FmpMarketDataProvider(client, api_key="placeholder-test-key", min_interval=0, retries=0)
        first = await provider.profile("SYN", identity=synthetic_identity())
        second = await provider.profile("SYN", identity=synthetic_identity(cik="0000000002", issuer_id="issuer-2", instrument_id="instrument-2"))
    assert first["cik"] == "1" and second["cik"] == "2"
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_provider_memory_is_bounded_after_many_distinct_securities():
    def handler(request):
        symbol = request.url.params["symbol"]
        if request.url.path.endswith("quote"):
            return httpx.Response(402)
        return httpx.Response(200, json=[{"symbol": symbol, "companyName": "Synthetic bounded memory"}])
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = FmpMarketDataProvider(client, api_key="placeholder-test-key", min_interval=0, retries=0)
        for index in range(1005):
            await provider.profile("SYN" + str(index))
            with pytest.raises(ProviderError):
                await provider.quote("SYN" + str(index))
        assert len(provider._profiles) == len(provider._access_denials) == 1000
        assert provider._endpoint_locks == provider._endpoint_users == {}


def test_scoped_provider_symbols_never_infer_dot_hyphen_aliases():
    identity = synthetic_identity(ticker="SYN.B")
    assert FmpMarketDataProvider._symbol("SYN.B", identity) == "SYN.B"
    assert FmpMarketDataProvider._symbol("SYN.B", {**identity, "provider_symbols": {"fmp": "SYN-B"}}) == "SYN-B"
