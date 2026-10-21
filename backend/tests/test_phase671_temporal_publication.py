"""Synthetic clock/proof tests; retained financial values are never refreshed."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.ai.bindings import binding_kinds
from app.ai.evidence import EvidenceRegistry, same_security, security_identity as ai_identity
from app.registry.service import SecurityRegistryService
from app.schemas.company import SearchResult
from app.services.security_identity import cache_scope
from app.services.cache_service import CacheService
from app.valuation.coverage import enrich_valuation_coverage
from app.valuation.automatic import prepare_automatic_inputs
from app.valuation.engine import calculate_valuation
from app.valuation.financial_currentness import source_cache_policy
from app.valuation.schemas import ValuationResponse
from test_automatic_evidence_fixture import examples
from test_api import client  # noqa: F401 -- isolated mocked API fixture
from test_phase65_analysis_identity import attach, synthetic_identity
from test_phase65_ai_identity import ScopedValuations, assembler
from test_valuation_engine import synthetic_inputs  # noqa: F401 -- isolated synthetic canonical inputs


CLOCK = datetime(2026, 10, 20, 12, tzinfo=UTC)


def retained_inputs():
    """Reconstruct original excerpts; never inherit another test's edits."""
    return {symbol: prepare_automatic_inputs(inputs, evidence) for symbol, (inputs, evidence) in examples().items()}


def resolve_proofs(monkeypatch, *, listing_day="2026-10-20", issuer_day="2026-10-20", clock=CLOCK):
    import app.registry.service as module
    monkeypatch.setattr(module, "utcnow", lambda: clock)
    registry = SecurityRegistryService.__new__(SecurityRegistryService)
    registry.settings = SimpleNamespace(registry_cache_ttl_seconds=86400)
    identity = synthetic_identity(ticker="MSFT", security_form="common_stock", issuer_business_category="operating_company",
        registry_as_of=listing_day, registry_retrieved_at="2026-10-20T11:30:00Z",
        listing_verification={"status": "verified", "confidence": "source_backed", "source": "synthetic-listing-authority",
            "observed_on": listing_day, "published_at": "1020202607:00", "source_timezone": None,
            "retrieved_at": "2026-10-20T11:30:00Z", "record_hash": "a" * 64,
            "issuer_linkage": {"source": "synthetic-sec-reference", "observed_on": issuer_day,
                "retrieved_at": "2026-10-20T11:45:00Z", "published_at": None,
                "issuer_id": "issuer-test-1", "cik": "0000000001", "ticker": "MSFT", "exchange_mic": "XNAS"}})
    return registry, identity, registry._with_freshness(identity)


@pytest.mark.parametrize("listing_day,issuer_day,expired", [
    ("2026-10-19", "2026-10-20", {"listing"}),
    ("2026-10-20", "2026-10-19", {"issuer_linkage"}),
    ("2026-10-19", "2026-10-19", {"listing", "issuer_linkage"}),
])
def test_exact_expired_proof_is_explicit_without_rewriting_original_status(monkeypatch, listing_day, issuer_day, expired):
    _registry, raw, selected = resolve_proofs(monkeypatch, listing_day=listing_day, issuer_day=issuer_day)
    assert selected["verification_state"] == "verification_expired"
    assert {key for key, record in selected["proof_expiry"].items() if record["state"] == "verification_expired"} == expired
    assert selected["listing_verification"]["status"] == raw["listing_verification"]["status"] == "verified"
    assert selected["proof_expiry"]["listing"]["observed_on"] == listing_day
    assert selected["proof_expiry"]["issuer_linkage"]["observed_on"] == issuer_day
    assert selected["proof_expiry"]["listing"]["published_at"] == "1020202607:00"
    assert selected["proof_expiry"]["listing"]["retrieved_at"] == "2026-10-20T11:30:00Z"
    assert selected["proof_expiry"]["issuer_linkage"]["retrieved_at"] == "2026-10-20T11:45:00Z"
    assert selected["identity_status"] == ("reference_only" if "issuer_linkage" in expired else "verified")


def test_original_ttl_boundary_and_cache_scope_are_exact(monkeypatch):
    boundary = datetime(2026, 10, 21, tzinfo=UTC)
    _registry, raw, current = resolve_proofs(monkeypatch, clock=boundary)
    _registry, _raw, expired = resolve_proofs(monkeypatch, clock=boundary + timedelta(microseconds=1))
    assert current["verification_state"] == "verified"
    assert expired["verification_state"] == "verification_expired"
    assert current["proof_expiry"]["listing"]["expires_at"] == boundary.isoformat()
    assert current["proof_expiry"]["listing"]["ttl_seconds"] == 86400
    assert cache_scope(current) != cache_scope(expired)
    assert current["listing_id"] == expired["listing_id"] == raw["listing_id"]


@pytest.mark.parametrize("mutation", ["missing", "future", "wrong_issuer", "wrong_cik", "wrong_venue", "wrong_symbol"])
def test_invalid_ownership_cannot_be_mislabeled_as_merely_expired_or_verified(monkeypatch, mutation):
    registry, raw, _selected = resolve_proofs(monkeypatch)
    if mutation == "missing":
        raw["listing_verification"].pop("issuer_linkage")
    else:
        field, value = {"future": ("observed_on", "2026-10-21"), "wrong_issuer": ("issuer_id", "another-issuer"),
            "wrong_cik": ("cik", "0000000002"), "wrong_venue": ("exchange_mic", "XNYS"),
            "wrong_symbol": ("ticker", "OTHER")}[mutation]
        raw["listing_verification"]["issuer_linkage"][field] = value
    selected = registry._with_freshness(raw)
    assert selected["verification_state"] == "unverified"
    assert selected["proof_expiry"]["issuer_linkage"]["state"] == "unverified"
    assert selected["identity_status"] == "reference_only"


def test_fresh_quote_and_filing_cannot_renew_source_proof(monkeypatch):
    registry, raw, _selected = resolve_proofs(monkeypatch, listing_day="2026-10-19", issuer_day="2026-10-19")
    before = deepcopy(raw)
    raw.update(price_timestamp=CLOCK.isoformat(), financial_retrieved_at=CLOCK.isoformat(),
               registry_retrieved_at=CLOCK.isoformat())
    selected = registry._with_freshness(raw)
    assert selected["verification_state"] == "verification_expired"
    assert selected["listing_verification"] == registry._with_freshness(before)["listing_verification"]
    assert selected["proof_expiry"]["listing"]["observed_on"] == "2026-10-19"


def current_mock_inputs(monkeypatch):
    """Synthetic policy proof tests the contract, not real reporting currentness."""
    import app.valuation.financial_currentness as module
    inputs = deepcopy(retained_inputs()["MSFT"])
    _registry, _raw, company = resolve_proofs(monkeypatch)
    inputs["company"].update(company)
    retrieved = CLOCK - timedelta(hours=1)
    inputs["financial_retrieved_at"] = retrieved.isoformat()
    expected_period = {key: inputs["reporting_period"][key] for key in ("start_date", "end_date")}
    expected_dates = tuple(expected_period[key] for key in ("start_date", "end_date"))
    filing = next(record for fact in inputs["facts"].values() for record in fact.get("provenance", [])
                  if record.get("end") == inputs["reporting_period"]["end_date"])
    proof = {"status": "current", "policy_id": "synthetic-currentness-contract-only", "assessed_at": CLOCK.isoformat(),
        "valid_until": (CLOCK + timedelta(hours=1)).isoformat(), "latest_applicable_period": expected_period,
        "filing": {"accession": filing["accn"], "filed_at": filing["filed"], "form": "10-K", "cik": company["cik"]},
        "source": {"provider": "synthetic-currentness-fixture", "url": "https://example.test/synthetic-filing-index",
                   "document_hash": "b" * 64, "observed_at": (CLOCK - timedelta(hours=2)).isoformat(),
                   "retrieved_at": retrieved.isoformat()}}
    def synthetic_policy(_inputs, assessment, _clock):
        return (assessment["source"]["provider"] == "synthetic-currentness-fixture"
                and tuple(assessment["latest_applicable_period"][key] for key in ("start_date", "end_date")) == expected_dates)
    monkeypatch.setitem(module.REVIEWED_FINANCIAL_CURRENTNESS_POLICIES, proof["policy_id"], synthetic_policy)
    inputs["financial_source_status"] = {"status": "fresh", "currentness": proof,
        "source_cache": source_cache_policy(retrieved, 21600, actual_expires_at=retrieved + timedelta(seconds=21600))}
    inputs["market"] = {"provider": "synthetic-market", "price": 100, "currency": "USD", "status": "fresh",
                        "price_timestamp": "2026-10-20T11:00:00Z", "retrieved_at": "2026-10-20T11:05:00Z"}
    return inputs


def test_current_publication_is_a_separate_positive_contract_not_a_formula_change(monkeypatch):
    inputs = current_mock_inputs(monkeypatch)
    original = calculate_valuation(inputs)
    result = enrich_valuation_coverage(inputs, original, as_of=CLOCK)
    assert result["financial_coverage"]["publication"]["result_type"] == "current_eligible"
    assert result["financial_coverage"]["publication"]["financial_currentness"]["status"] == "current"
    assert result["financial_coverage"]["stages"]["published_fair_value"]["status"] == "available"
    for name, case in result["scenarios"].items():
        assert case["summary"] == original["scenarios"][name]["summary"]
        assert case["publication"]["clocks"]["quote"]["observed_at"] == "2026-10-20T11:00:00Z"
        assert case["publication"]["clocks"]["quote"]["retrieved_at"] == "2026-10-20T11:05:00Z"


@pytest.mark.parametrize("mutation,code", [
    ("old_quote", "current_provider_quote_unavailable"),
    ("fresh_retrieval_old_quote", "current_provider_quote_unavailable"),
    ("missing_financial_status", "financial_source_currentness_unverified"),
    ("incompatible_currency", "publication_currency_unverified"),
    ("unverified_shares", "publication_share_basis_unverified"),
    ("future_filing", "financial_source_dates_unverified"),
    ("expired_during_calculation", "listing_verification_expired"),
    ("future_financial_retrieval", "financial_acquisition_clock_unverified"),
    ("missing_quote_retrieval", "current_provider_quote_unavailable"),
    ("future_quote_retrieval", "current_provider_quote_unavailable"),
    ("quote_observed_after_retrieval", "current_provider_quote_unavailable"),
    ("future_proof_retrieval", "listing_verification_unavailable"),
])
def test_valid_intrinsic_output_does_not_imply_current_publication(monkeypatch, mutation, code):
    inputs = current_mock_inputs(monkeypatch)
    original = calculate_valuation(inputs)
    if mutation in {"old_quote", "fresh_retrieval_old_quote"}:
        inputs["market"]["price_timestamp"] = "2026-01-01T12:00:00Z"
        if mutation == "fresh_retrieval_old_quote":
            inputs["market"]["retrieved_at"] = CLOCK.isoformat()
    elif mutation == "missing_financial_status":
        inputs.pop("financial_source_status")
    elif mutation == "incompatible_currency":
        inputs["market"]["currency"] = "EUR"
    elif mutation == "unverified_shares":
        inputs["basis"]["share_basis_verified"] = False
    elif mutation == "future_filing":
        next(iter(inputs["facts"].values()))["provenance"][0]["filed"] = "2026-10-21"
    elif mutation == "future_financial_retrieval":
        inputs["financial_retrieved_at"] = "2026-10-21T12:00:00Z"
    elif mutation == "missing_quote_retrieval":
        inputs["market"].pop("retrieved_at")
    elif mutation == "future_quote_retrieval":
        inputs["market"]["retrieved_at"] = "2026-10-21T12:00:00Z"
    elif mutation == "quote_observed_after_retrieval":
        inputs["market"]["retrieved_at"] = "2026-10-20T10:00:00Z"
    elif mutation == "future_proof_retrieval":
        inputs["company"]["proof_expiry"]["listing"]["retrieved_at"] = "2026-10-21T12:00:00Z"
    clock = CLOCK + timedelta(days=1) if mutation == "expired_during_calculation" else CLOCK
    result = enrich_valuation_coverage(inputs, original, as_of=clock)
    status = result["financial_coverage"]["publication"]
    assert status["result_type"] == "historical_illustration"
    assert code in {item["code"] for item in status["blockers"]}
    assert result["scenarios"]["base"]["summary"] == original["scenarios"]["base"]["summary"]
    assert result["financial_coverage"]["stages"]["published_fair_value"]["status"] == "unavailable"


@pytest.mark.parametrize("ticker,value", [("AAPL", 214.2302568301956), ("MSFT", 619.5604742486083), ("NVDA", None), ("ORCL", None)])
def test_retained_historical_values_and_unavailable_states_remain_exact(ticker, value):
    inputs = deepcopy(retained_inputs()[ticker])
    result = enrich_valuation_coverage(inputs, calculate_valuation(inputs), as_of=CLOCK)
    assert result["scenarios"]["base"]["summary"]["fair_value"] == value
    assert result["financial_coverage"]["publication"]["result_type"] == ("unavailable" if value is None else "historical_illustration")


def test_scenario_null_output_never_inherits_historical_publication(monkeypatch):
    inputs = current_mock_inputs(monkeypatch)
    original = calculate_valuation(inputs)
    original["scenarios"]["bear"]["summary"]["fair_value"] = None
    result = enrich_valuation_coverage(inputs, original, as_of=CLOCK)
    assert result["scenarios"]["base"]["publication"]["result_type"] == "current_eligible"
    assert result["scenarios"]["bear"]["publication"]["result_type"] == "unavailable"


def test_recent_cache_of_ancient_reporting_data_cannot_establish_current_eligibility(monkeypatch):
    inputs = current_mock_inputs(monkeypatch)
    original = calculate_valuation(inputs)
    inputs["reporting_period"].update(start_date="2001-01-01", end_date="2001-12-31", fiscal_year=2001)
    for fact in inputs["facts"].values():
        for record in fact.get("provenance", []):
            record["filed"] = "2002-02-15"
    inputs["financial_source_status"].pop("currentness")
    result = enrich_valuation_coverage(inputs, original, as_of=CLOCK)
    publication = result["financial_coverage"]["publication"]
    assert publication["result_type"] == "historical_illustration"
    assert "financial_currentness_policy_unavailable" in publication["financial_currentness"]["reason_codes"]
    assert "financial_period_currentness_unverified" in {item["code"] for item in publication["blockers"]}
    assert result["scenarios"]["base"]["summary"] == original["scenarios"]["base"]["summary"]


@pytest.mark.asyncio
async def test_cache_configuration_change_cannot_extend_original_source_expiry(session_factory):
    cache = CacheService(session_factory)
    async def original():
        return {"synthetic": True}
    first = await cache.get_or_load("synthetic-original-expiry", 60, "sec-edgar", original)
    async def forbidden():
        pytest.fail("A still-valid original cache hit must not refresh its source.")
    later = await cache.get_or_load("synthetic-original-expiry", 21600, "sec-edgar", forbidden)
    assert later.retrieved_at == first.retrieved_at
    assert later.expires_at == first.expires_at
    policy = source_cache_policy(later.retrieved_at, 21600, actual_expires_at=later.expires_at)
    assert policy["expires_at"] == first.expires_at.isoformat()
    assert policy["expires_at"] != policy["configured_expires_at"]
    assert source_cache_policy(first.retrieved_at, 21600)["expires_at"] is None


@pytest.mark.asyncio
async def test_normalized_cache_keeps_upstream_original_expiry_across_hits(client, raw_facts):
    cache = client.app.state.financial_service.cache
    cache._write("sec:facts:0000000001", raw_facts, 60, "sec-edgar")
    raw_expiry = cache._read("sec:facts:0000000001").expires_at
    service = client.app.state.financial_service
    _company, first, _warnings, _status = await service.dataset("MSFT")
    _company, second, _warnings, _status = await service.dataset("MSFT")
    from app.core.database import as_utc
    assert first.expires_at == second.expires_at == as_utc(raw_expiry)
    assert second.payload["_source_cache_provenance"]["expires_at"] == first.expires_at.isoformat()


@pytest.mark.parametrize("mutation,reason", [
    ("unreviewed_policy", "financial_currentness_policy_unavailable"),
    ("expired_assessment", "financial_currentness_assessment_expired_or_unverified"),
    ("expired_source_cache", "financial_source_cache_expired_or_unverified"),
    ("extended_assessment", "financial_currentness_assessment_expired_or_unverified"),
    ("extended_source_cache", "financial_source_cache_expired_or_unverified"),
    ("missing_source_cache_ttl", "financial_source_cache_expired_or_unverified"),
    ("period_mismatch", "financial_currentness_period_mismatch"),
    ("unknown_filing", "financial_currentness_filing_unverified"),
    ("source_missing", "financial_currentness_source_unverified"),
])
def test_financial_currentness_proof_and_original_source_cache_boundaries_are_required(monkeypatch, mutation, reason):
    inputs = current_mock_inputs(monkeypatch)
    original = calculate_valuation(inputs)
    status = inputs["financial_source_status"]
    proof = status["currentness"]
    clock = CLOCK
    if mutation == "unreviewed_policy":
        proof["policy_id"] = "not-a-reviewed-policy"
    elif mutation == "expired_assessment":
        clock += timedelta(hours=1, microseconds=1)
    elif mutation == "expired_source_cache":
        clock += timedelta(hours=5, microseconds=1)
    elif mutation == "extended_assessment":
        proof["valid_until"] = (CLOCK + timedelta(days=2)).isoformat()
    elif mutation == "extended_source_cache":
        status["source_cache"]["expires_at"] = (CLOCK + timedelta(days=2)).isoformat()
    elif mutation == "missing_source_cache_ttl":
        status["source_cache"].pop("ttl_seconds")
    elif mutation == "period_mismatch":
        proof["latest_applicable_period"] = {"start_date": "2001-01-01", "end_date": "2001-12-31"}
    elif mutation == "unknown_filing":
        proof["filing"]["accession"] = "unknown-filing"
    elif mutation == "source_missing":
        proof["source"] = {}
    result = enrich_valuation_coverage(inputs, original, as_of=clock)
    publication = result["financial_coverage"]["publication"]
    assert publication["result_type"] == "historical_illustration"
    assert reason in publication["financial_currentness"]["reason_codes"]
    assert result["scenarios"]["base"]["summary"] == original["scenarios"]["base"]["summary"]


def test_api_schema_preserves_additive_clock_metadata(monkeypatch, client):
    _registry, _raw, company = resolve_proofs(monkeypatch, listing_day="2026-10-19")
    parsed = SearchResult.model_validate(company).model_dump(mode="json")
    assert parsed["verification_state"] == "verification_expired"
    assert parsed["proof_expiry"]["listing"]["source"] == "synthetic-listing-authority"
    result = client.get("/api/stocks/MSFT/valuation/defaults")
    assert result.status_code == 200
    model = ValuationResponse.model_validate(result.json()).model_dump(mode="json")
    assert all(case["publication"]["result_type"] in {"historical_illustration", "current_eligible", "unavailable"}
               for case in model["scenarios"].values())
    currentness = model["financial_coverage"]["publication"]["financial_currentness"]
    assert currentness["status"] == "unverified"
    assert currentness["assessment"]["status"] == "unverified"


def test_expired_identity_is_visible_in_profile_and_scoped_valuation_api(monkeypatch, client):
    _registry, _raw, company = resolve_proofs(monkeypatch, listing_day="2026-10-19", issuer_day="2026-10-19")
    attach(client, **company)
    path = "/api/stocks/MSFT?instrument_id=" + company["instrument_id"]
    profile = client.get(path)
    assert profile.status_code == 200
    assert profile.json()["company"]["verification_state"] == "verification_expired"
    assert profile.json()["company"]["proof_expiry"] == company["proof_expiry"]
    valuation = client.get("/api/stocks/MSFT/valuation/defaults", params={"instrument_id": company["instrument_id"]})
    assert valuation.status_code == 200
    body = valuation.json()
    assert body["company"]["verification_state"] == "verification_expired"
    assert body["financial_coverage"]["publication"]["result_type"] == "unavailable"
    assert all(model["status"] != "valid" for model in body["scenarios"]["base"]["models"])


def test_expiry_changes_ai_identity_and_remains_citation_only(monkeypatch):
    _registry, _raw, current = resolve_proofs(monkeypatch)
    _registry, _raw, expired = resolve_proofs(monkeypatch, clock=CLOCK + timedelta(days=1))
    left, right = ai_identity(current), ai_identity(expired)
    assert left != right and not same_security(left, right)
    registry = EvidenceRegistry("MSFT", identity=right)
    key = registry.add(category="company_profile", provider="synthetic", title="Dated listing proof",
        metric="listing_verification", value={"verification": right}, unit="structured")
    assert binding_kinds(registry.registry[key]) == ()


@pytest.mark.asyncio
async def test_expired_proof_metadata_survives_bounded_ai_assembly_without_becoming_numeric(monkeypatch, synthetic_inputs):
    _registry, _raw, company = resolve_proofs(monkeypatch, listing_day="2026-10-19", issuer_day="2026-10-19")
    values = ScopedValuations(synthetic_inputs)
    values.data["company"].update(company)
    result = await assembler(values).assemble("MSFT", instrument_id=company["instrument_id"])
    assert result["identity"]["verification_state"] == "verification_expired"
    assert result["identity"]["proof_expiry"]["issuer_linkage"]["state"] == "verification_expired"
    proofs = [record for record in result["registry"].values() if record["metric"] == "listing_verification"]
    assert len(proofs) == 1 and binding_kinds(proofs[0]) == ()
    assert proofs[0]["value"]["verification_state"] == "verification_expired"
    assert proofs[0]["value"]["proof_expiry"] == result["identity"]["proof_expiry"]
    assert all(record["identity"] == result["identity"] for record in result["registry"].values())
