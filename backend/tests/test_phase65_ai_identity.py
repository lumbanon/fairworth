"""Synthetic securities and mocked generation only; no new provider observations."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.ai.context import EvidenceContextAssembler
from app.ai.evidence import EvidenceRegistry, security_identity
from app.ai.schemas import ChatDraft, ChatRequest, ReportRequest
from app.core.exceptions import ApiError
from app.main import create_app
from app.valuation.engine import calculate_valuation
from test_ai_research_service import configured, finding, package, service
from test_valuation_engine import synthetic_inputs


def identity(instrument="class-a", issuer="synthetic-issuer"):
    return {"issuer_id": issuer, "instrument_id": instrument, "listing_id": "listing-" + instrument,
            "cik": None, "ticker": "SYN", "exchange": "TEST", "instrument_type": "common_stock",
            "listing_status": "active", "identity_status": "verified", "share_class": instrument}


def scoped_package(instrument="class-a", issuer="synthetic-issuer", listing=None):
    result = package("SYN")
    result["identity"] = identity(instrument, issuer)
    if listing is not None:
        result["identity"]["listing_id"] = listing
    for item in result["registry"].values():
        item["identity"] = deepcopy(result["identity"])
        item["source_url"] = None  # The synthetic fixture asserts no real source identity.
    return result


def scoped_service():
    target = service()
    async def assemble(_ticker, _valuation, instrument_id=None, listing_id=None):
        return scoped_package(instrument_id, listing=listing_id)
    target.assembler.assemble.side_effect = assemble
    return target


class ScopedValuations:
    def __init__(self, data):
        self.data = deepcopy(data)
        self.data["company"].update(identity())
        self.calls = []

    async def inputs(self, ticker, instrument_id=None, listing_id=None):
        self.calls.append(("inputs", ticker, instrument_id, listing_id))
        return deepcopy(self.data)

    async def calculate(self, ticker, request, instrument_id=None, listing_id=None):
        self.calls.append(("calculate", ticker, instrument_id, listing_id))
        return calculate_valuation(deepcopy(self.data), request)


def assembler(values, companies=None, financials=None):
    return EvidenceContextAssembler(values, companies, financials, None,
                                    SimpleNamespace(ai_max_context_tokens=52000))


@pytest.mark.asyncio
async def test_selected_security_reaches_engine_and_every_evidence_record(synthetic_inputs):
    values = ScopedValuations(synthetic_inputs)
    result = await assembler(values).assemble("SYN", instrument_id="class-a")
    assert result["identity"] == security_identity(values.data["company"])
    assert values.calls == [("inputs", "SYN", "class-a", None), ("calculate", "SYN", "class-a", None)]
    assert all(item["identity"] == result["identity"] for item in result["registry"].values())
    assert "financial-evidence-4" == result["evidence_adapter_version"]


@pytest.mark.asyncio
async def test_assembler_rejects_wrong_class_even_when_ticker_and_cik_match(synthetic_inputs):
    values = ScopedValuations(synthetic_inputs)
    with pytest.raises(ApiError) as error:
        await assembler(values).assemble("SYN", instrument_id="class-b")
    assert error.value.code == "incompatible_financial_identity"


@pytest.mark.parametrize("field,value", [("issuer_id", "other"), ("instrument_id", "other"),
                                         ("listing_id", "other"), ("cik", "0000000001")])
@pytest.mark.asyncio
async def test_assembler_rejects_mixed_valuation_identity(synthetic_inputs, field, value):
    values = ScopedValuations(synthetic_inputs)
    original = values.calculate
    async def calculate(*args, **kwargs):
        result = await original(*args, **kwargs)
        result["company"][field] = value
        return result
    values.calculate = calculate
    with pytest.raises(ApiError) as error:
        await assembler(values).assemble("SYN", instrument_id="class-a")
    assert error.value.code == "incompatible_financial_identity"


def test_equal_values_in_distinct_securities_have_distinct_evidence_ids():
    kwargs = {"category": "reported_fact", "provider": "synthetic", "title": "Synthetic revenue",
              "metric": "revenue", "value": 100, "unit": "USD", "period": "FY2025"}
    ids = [EvidenceRegistry("SYN", identity(instrument, issuer)).add(**kwargs)
           for instrument, issuer in [("a", "issuer-a"), ("b", "issuer-a"), ("a", "issuer-b")]]
    assert len(set(ids)) == 3
    legacy = EvidenceRegistry("SYN")
    key = legacy.add(**kwargs)
    assert "identity" not in legacy.registry[key]


@pytest.mark.asyncio
async def test_report_cache_and_evidence_capabilities_isolate_share_classes():
    target = scoped_service()
    first = await target.report("SYN", ReportRequest(), "owner", "class-a")
    cached = await target.report("SYN", ReportRequest(), "owner", "class-a")
    second = await target.report("SYN", ReportRequest(), "owner", "class-b")
    assert cached["cache_status"] == "hit"
    assert first["snapshot_token"] != second["snapshot_token"]
    assert target.client.generate.await_count == 2
    assert first["identity"]["instrument_id"] == "class-a"
    assert second["identity"]["instrument_id"] == "class-b"
    assert target.evidence("SYN", "e_revenue", first["snapshot_token"], "owner", "class-a")["value"] == 100
    for selected in (None, "class-b"):
        with pytest.raises(ApiError) as error:
            target.evidence("SYN", "e_revenue", cached["snapshot_token"], "owner", selected)
        assert error.value.code == "ai_evidence_not_found"
    await target.close()


@pytest.mark.parametrize("mutation", ["missing_record_identity", "other_issuer", "other_class", "other_listing", "other_cik", "wrong_package"])
@pytest.mark.asyncio
async def test_mixed_or_missing_scoped_evidence_is_rejected_before_generation(mutation):
    target = service()
    data = scoped_package()
    record = data["registry"]["e_revenue"]
    if mutation == "missing_record_identity":
        record.pop("identity")
    elif mutation == "wrong_package":
        data["identity"] = identity("class-b")
    else:
        field = {"other_issuer": "issuer_id", "other_class": "instrument_id",
                 "other_listing": "listing_id", "other_cik": "cik"}[mutation]
        record["identity"][field] = "other"
    target.assembler.assemble.return_value = data
    with pytest.raises(ApiError) as error:
        await target.report("SYN", ReportRequest(), "owner", "class-a")
    assert error.value.code == "ai_identity_mismatch"
    target.client.generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_profile_only_context_has_identity_and_no_invented_financials():
    unavailable = ApiError("financial_data_unavailable", "Synthetic statements absent.", 404)
    values = SimpleNamespace(inputs=AsyncMock(side_effect=unavailable), calculate=AsyncMock(side_effect=unavailable))
    companies = SimpleNamespace(profile=AsyncMock(return_value={"company": {**identity(), "name": "Synthetic profile-only security"}}))
    financials = SimpleNamespace(dataset=AsyncMock(side_effect=unavailable))
    result = await assembler(values, companies, financials).assemble("SYN", instrument_id="class-a")
    assert result["identity"]["instrument_id"] == "class-a"
    assert all(item["value"] is None for item in result["registry"].values()
               if item["metric"] in {"revenue", "total_debt", "market_price", "base_fair_value"})
    assert any("only registered profile evidence" in item for item in result["limitations"])
    companies.profile.assert_awaited_once_with("SYN", instrument_id="class-a")
    financials.dataset.assert_awaited_once_with("SYN", instrument_id="class-a")


def test_scoped_chat_api_publishes_and_retrieves_matching_identity(engine, fake_providers):
    app = create_app(configured(database_url="sqlite://"), engine=engine, providers=fake_providers)
    with TestClient(app) as client:
        target = scoped_service()
        target.client.generate.return_value = ChatDraft(answer=[finding()])
        app.state.research_service = target
        headers = {"X-Fairworth-Session": "synthetic-security-session"}
        path = "/api/stocks/SYN/ai/chat?instrument_id=class-a"
        response = client.post(path, json={"question": "Explain the available evidence."}, headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["identity"]["instrument_id"] == "class-a"
        assert body["evidence_references"][0]["identity"] == body["identity"]
        evidence = "/api/stocks/SYN/ai/evidence/e_revenue?snapshot_token=" + body["snapshot_token"]
        assert client.get(evidence + "&instrument_id=class-a", headers=headers).status_code == 200
        assert client.get(evidence + "&instrument_id=class-b", headers=headers).status_code == 404
        assert client.get(evidence, headers=headers).status_code == 404
        assert client.post(path.replace("class-a", "bad%20id"), json={"question": "Explain."}, headers=headers).status_code == 422


@pytest.mark.asyncio
async def test_scoped_chat_keeps_independent_numerical_validation():
    target = scoped_service()
    invalid = finding()
    invalid.explanation = "Revenue was $999 billion."
    target.client.generate.return_value = ChatDraft(answer=[invalid])
    with pytest.raises(ApiError) as error:
        await target.chat("SYN", ChatRequest(question="Explain revenue."), "owner", "class-a")
    assert error.value.code == "unsupported_ai_number"
    assert not target.snapshots


@pytest.mark.asyncio
async def test_listing_selector_reaches_inputs_and_calculation(synthetic_inputs):
    values = ScopedValuations(synthetic_inputs)
    result = await assembler(values).assemble("SYN", instrument_id="class-a", listing_id="listing-class-a")
    assert all(call[2:] == ("class-a", "listing-class-a") for call in values.calls)
    assert result["identity"]["listing_id"] == "listing-class-a"
    assert all(item["identity"]["listing_id"] == "listing-class-a" for item in result["registry"].values())
    with pytest.raises(ApiError) as error:
        await assembler(values).assemble("SYN", instrument_id="class-a", listing_id="other-venue")
    assert error.value.code == "incompatible_financial_identity"


@pytest.mark.asyncio
async def test_report_cache_and_capabilities_isolate_two_listings_of_same_instrument():
    target = scoped_service()
    a = await target.report("SYN", ReportRequest(), "owner", "class-a", "venue-a")
    cached = await target.report("SYN", ReportRequest(), "owner", "class-a", "venue-a")
    b = await target.report("SYN", ReportRequest(), "owner", "class-a", "venue-b")
    assert cached["cache_status"] == "hit"
    assert target.client.generate.await_count == 2
    assert a["snapshot_token"] != b["snapshot_token"]
    assert target.evidence("SYN", "e_revenue", a["snapshot_token"], "owner", "class-a", "venue-a")["identity"]["listing_id"] == "venue-a"
    with pytest.raises(ApiError) as error:
        target.evidence("SYN", "e_revenue", a["snapshot_token"], "owner", "class-a", "venue-b")
    assert error.value.code == "ai_evidence_not_found"
    await target.close()


@pytest.mark.asyncio
async def test_wrong_requested_listing_fails_before_mock_generation():
    target = service()
    target.assembler.assemble.return_value = scoped_package()
    with pytest.raises(ApiError) as error:
        await target.chat("SYN", ChatRequest(question="Explain the evidence."), "owner", "class-a", "other-venue")
    assert error.value.code == "ai_identity_mismatch"
    target.client.generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_company_alias_cannot_bind_a_scoped_security_but_explicit_symbol_alias_can(synthetic_inputs):
    values = ScopedValuations(synthetic_inputs)
    values.data["company"]["aliases"] = ["QUERY"]
    with pytest.raises(ApiError) as error:
        await assembler(values).assemble("QUERY", instrument_id="class-a")
    assert error.value.code == "incompatible_financial_identity"
    values.data["company"]["symbol_aliases"] = ["QUERY"]
    result = await assembler(values).assemble("QUERY", instrument_id="class-a")
    assert result["ticker"] == "QUERY" and result["identity"]["ticker"] == "SYN"


def test_listing_query_chat_api_enforces_citation_listing(engine, fake_providers):
    app = create_app(configured(database_url="sqlite://"), engine=engine, providers=fake_providers)
    with TestClient(app) as client:
        target = scoped_service()
        target.client.generate.return_value = ChatDraft(answer=[finding()])
        app.state.research_service = target
        headers = {"X-Fairworth-Session": "synthetic-listing-session"}
        response = client.post("/api/stocks/SYN/ai/chat?instrument_id=class-a&listing_id=venue-a",
                               json={"question": "Explain the evidence."}, headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["identity"]["listing_id"] == "venue-a"
        url = "/api/stocks/SYN/ai/evidence/e_revenue?snapshot_token=" + body["snapshot_token"] + "&instrument_id=class-a&listing_id="
        assert client.get(url + "venue-a", headers=headers).status_code == 200
        assert client.get(url + "venue-b", headers=headers).status_code == 404
