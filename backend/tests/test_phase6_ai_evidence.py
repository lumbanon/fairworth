"""New deterministic diagnostics stay exact and use the unchanged binding gates."""
from copy import deepcopy
import json
from types import SimpleNamespace

import httpx
import pytest

from app.ai.bindings import binding_kinds
from app.ai.context import EVIDENCE_ADAPTER_VERSION, _valuation_identity
from app.ai.evidence import stable_snapshot_id
from app.ai.schemas import ChatRequest, ResearchAnswer
from app.valuation.engine import calculate_valuation
from app.valuation.inputs import normalize_annual_period
from app.valuation.schemas import ValuationRequest
from test_ai_evidence_context import Valuations, assembler, find
from test_phase6_normalization import retained
from test_valuation_engine import synthetic_inputs  # noqa: F401 - explicitly synthetic, not issuer data


@pytest.fixture(autouse=True)
def no_real_http(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Real HTTP is prohibited in Phase 6 AI regressions.")
    async def async_blocked(*args, **kwargs):
        blocked()
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", async_blocked)


@pytest.mark.parametrize("ticker", ["AAPL", "MSFT", "NVDA", "ORCL"])
@pytest.mark.asyncio
async def test_exact_new_model_counts_and_structured_diagnostics_use_independent_bindings(ticker):
    service = Valuations(ticker)
    result = calculate_valuation(deepcopy(service.data))
    package = await assembler(service, budget=90000).assemble(ticker)
    diagnostics = result["scenarios"]["base"]["diagnostics"]
    assert package["evidence_adapter_version"] == EVIDENCE_ADAPTER_VERSION
    assert find(package, "base_eligible_model_count")["value"] == diagnostics["coverage"]["eligible_count"]
    assert find(package, "base_method_family_count")["value"] == diagnostics["coverage"]["method_family_count"]
    assert "value" in binding_kinds(find(package, "base_method_family_count"))
    structured = find(package, "base_valuation_diagnostics")
    assert structured["value"] == diagnostics
    assert binding_kinds(structured) == ()
    for endpoint in ("minimum", "maximum"):
        source_range = diagnostics["aggregation"]["estimate_range"]
        if source_range:
            item = find(package, f"base_estimate_range_{endpoint}")
            assert item["value"] == source_range[endpoint]
            assert item["unit"] == "USD/share"
            assert "value" in binding_kinds(item)


@pytest.mark.asyncio
async def test_additional_dated_facts_retain_exact_units_accessions_and_source_classification():
    service = Valuations("MSFT")
    company, annual = retained("MSFT")
    facts = normalize_annual_period(annual, "USD", company["retrieved_at"])["facts"]
    for field in ("stock_based_compensation", "finance_lease_liability"):
        service.data["facts"][field] = facts[field]
    before = deepcopy(service.data)
    package = await assembler(service, budget=90000).assemble("MSFT")
    stock = find(package, "stock_based_compensation")
    lease = find(package, "finance_lease_liability")
    assert stock["value"] == 12_405_000_000 and stock["unit"] == "USD"
    assert stock["category"] == "reported_fact" and stock["accession"]
    assert stock["period"] == find(package, "revenue")["period"]
    assert lease["value"] == 66_594_000_000 and lease["category"] == "reported_fact"
    assert lease["accession"] and lease["derivation"] is None
    assert service.data == before


@pytest.mark.asyncio
async def test_user_defined_model_range_and_manual_quote_keep_exact_classification(synthetic_inputs):
    service = Valuations()
    service.data = deepcopy(synthetic_inputs)
    service.data["market"] = {"price": 110, "currency": "USD", "provider": "synthetic-market",
        "price_timestamp": "2026-10-13T20:00:00Z", "retrieved_at": "2026-10-14T00:00:00Z",
        "status": "partial", "warnings": []}
    request = ValuationRequest(assumptions={"forward_eps": 5, "target_pe": 20,
        "forecast_revenue": 1000, "target_ev_revenue": 1}, enabled_models=["pe", "evRevenue"],
        weights={"pe": 1, "evRevenue": 1}, manual_market_price={"value": 90.0, "currency": "USD"})
    package = await assembler(service, budget=90000).assemble("SYN", request)
    for endpoint, expected in (("minimum", 92), ("maximum", 100)):
        item = find(package, f"base_estimate_range_{endpoint}")
        assert item["value"] == expected and item["category"] == "user_assumption"
        assert item["unit"] == "USD/share" and "value" in binding_kinds(item)
    quote = find(package, "market_price")
    assert quote["category"] == "user_assumption" and quote["provider"] == "User"
    assert quote["observation_date"] is None and quote["retrieved_at"] is None
    assert "date" not in binding_kinds(quote)


def test_snapshot_identity_excludes_only_explicit_audit_clocks_and_keeps_financial_dates():
    before = {"confidence": {"assessed_as_of": "2026-10-13", "level": "low"},
              "data_completeness": {"as_of": "2026-10-13", "quote_observation_date": "2026-10-12"},
              "snapshot_dates": {"financial": "2026-10-13", "market": "2026-10-12"}}
    after = deepcopy(before)
    after["confidence"]["assessed_as_of"] = "2026-10-16"
    after["data_completeness"]["as_of"] = "2026-10-16"
    assert stable_snapshot_id(_valuation_identity(before)) == stable_snapshot_id(_valuation_identity(after))
    after["confidence"]["level"] = "moderate"
    assert stable_snapshot_id(_valuation_identity(before)) != stable_snapshot_id(_valuation_identity(after))
    after = deepcopy(before)
    after["snapshot_dates"]["market"] = "2026-10-11"
    assert stable_snapshot_id(_valuation_identity(before)) != stable_snapshot_id(_valuation_identity(after))


@pytest.mark.asyncio
async def test_exact_msft_question_passes_complete_mocked_request_and_public_response_validation():
    from test_ai_four_company import research
    service, values = research("MSFT")
    original = deepcopy(values.data)
    question = "Why is MSFT's valuation available or unavailable?"
    requests = []

    async def response(**kwargs):
        payload = json.loads(kwargs["input"][0]["content"])["untrusted_data"]
        assert payload["question"] == question and payload["history"] == []
        package = payload["evidence"]
        assert package["evidence_adapter_version"] == EVIDENCE_ADAPTER_VERSION
        requests.append(deepcopy(package))
        fair, count, model = (find(package, key) for key in ("base_fair_value", "base_contributing_model_count", "base_model_name"))
        quote, models = (find(package, key) for key in ("market_price", "base_model_results"))
        typed = {"answer": [{"title": "Availability and limits", "category": "policy_estimate", "uncertainty": "limited",
            "explanation": [{"kind": "text", "text": "The Python engine supplies an illustrative policy-based fair value of"},
                {"kind": "value", "evidence_id": fair["id"]}, {"kind": "text", "text": "from"},
                {"kind": "value", "evidence_id": count["id"]}, {"kind": "text", "text": "contributing model:"},
                {"kind": "model", "evidence_id": model["id"]}, {"kind": "text", "text": ". The comparison quote was observed"},
                {"kind": "date", "evidence_id": quote["id"]}, {"kind": "text", "text": ". Missing required inputs block alternative models; independent confirmation remains unavailable."}],
            "evidence_ids": [models["id"]], "quantitative_claims": []}]}
        return SimpleNamespace(status="completed", output_text=json.dumps(typed))

    service.client.sdk.responses.create = response
    result = await service.chat("MSFT", ChatRequest(question=question), "offline-phase6-owner")
    ResearchAnswer.model_validate(result)
    assert len(requests) == 1
    finding = result["answer"][0]
    assert finding["category"] == "policy_estimate" and finding["uncertainty"] == "limited"
    assert "fair value of $619.56 from 1 contributing model: Forward P/E." in finding["explanation"]
    assert len(finding["evidence_ids"]) == 5
    assert finding["quantitative_claims"][0]["value"] == 619.5604742486083
    for item in result["evidence_references"]:
        assert service.evidence("MSFT", item["id"], result["snapshot_token"], "offline-phase6-owner") == item
    assert values.data == original
    await service.close()
