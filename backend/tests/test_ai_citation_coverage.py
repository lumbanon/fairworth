"""Offline regressions for request-scoped, per-finding typed-reference coverage.

The captured MSFT reply is retained exactly. Completing its citation coverage
must not invent values, infer references from prose, or relax later validators.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import openai
import pytest
from pydantic import ValidationError

from app.ai.bindings import canonical_draft, generation_model
from app.ai.client import ResearchClient
from app.ai.prompts import CHAT_TASK
from app.ai.report_service import ResearchService
from app.ai.schemas import ChatDraft, ChatRequest, QuantitativeClaim, ResearchAnswer
from app.ai.validation import render_finding, validate_findings
from app.core.config import Settings
from app.core.exceptions import ApiError


FIXTURE = Path(__file__).parent / "fixtures" / "ai" / "msft_v7_citation_coverage_failure.json"
RAW_SHA = "bf8dc714a5545d55ec10c433879716d91afa35587e685c6b9467a006459f011b"


@pytest.fixture(autouse=True)
def no_real_http(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Real HTTP is prohibited in citation coverage tests.")

    async def async_blocked(*args, **kwargs):
        blocked()

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", async_blocked)


def capture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def raw(captured=None):
    return json.loads((captured or capture())["raw_output_text"])


def registry():
    return capture()["evidence_registry"]


def source_id(metric):
    return next(key for key, item in registry().items() if item["metric"] == metric)


def typed(value=None, sources=None):
    return generation_model(ChatDraft, {"registry": sources or registry()}).model_validate(value or raw())


def unchecked(value):
    """Exercise the canonical boundary independently of generation validation."""
    return SimpleNamespace(model_dump=lambda: deepcopy(value))


def canonical(value=None, sources=None):
    sources = sources or registry()
    return canonical_draft(ChatDraft, typed(value, sources), sources)


def configured():
    return Settings(_env_file=None, ai_research_enabled=True,
                    openai_api_key="fake-test-key-not-a-credential", openai_model="test-configured-model")


def evidence_package():
    return {"ticker": "MSFT", "company_name": "Microsoft Corporation", "registry": registry(),
            "financial_snapshot_id": "fixture-msft-financial", "valuation_snapshot_id": "fixture-msft-valuation",
            "snapshot_dates": {"financial": "2026-06-30", "valuation": "2026-10-16", "market": "2026-10-15"},
            "limitations": ["This is a dated, low-quality policy estimate with no independent model confirmation."]}


def test_exact_captured_reply_and_every_typed_reference_are_retained():
    saved = capture()
    assert saved["question"] == "Why is MSFT's valuation available or unavailable?"
    assert hashlib.sha256(saved["raw_output_text"].encode("utf-8")).hexdigest() == RAW_SHA
    assert saved["capture_provenance"]["original_text_sha256"] == RAW_SHA
    assert saved["capture_provenance"]["redacted"] is False
    assert saved["capture_provenance"]["approved_complete_request_sha256"] == "aae95b9f504a73eacc7d38ab32f95e3b7166e12b47852bb502bb01032e61032e"
    assert saved["capture_provenance"]["approved_generation_schema_sha256"] == "3f6bc036b10d029295f3c5c9eed2eed1e364b210cbbd33219ca3c0074fbadf54"
    assert len(saved["request_scope"]["evidence_ids"]) == 47
    assert len(saved["evidence_registry"]) == 10
    original = raw(saved)
    assert len(original["answer"]) == 2
    for finding, coverage in zip(original["answer"], saved["expected_citation_coverage"], strict=True):
        references = [{"part_index": index, "kind": part["kind"], "evidence_id": part["evidence_id"]}
                      for index, part in enumerate(finding["explanation"]) if part["kind"] != "text"]
        assert references == coverage["typed_references"]
        assert len(references) == 4
        for reference in references:
            assert reference["evidence_id"] in saved["request_scope"]["evidence_ids"]
            assert reference["evidence_id"] in saved["request_scope"]["binding_catalog"][reference["kind"]]
    second_values = [part["evidence_id"] for part in original["answer"][1]["explanation"] if part["kind"] == "value"]
    assert second_values.count(source_id("net_income")) == 3
    assert saved["original_failure"]["rule"] == "uncited_or_unknown_binding"


def test_captured_reply_derives_only_local_stable_unique_citations_and_exact_claims():
    saved = capture()
    sources = saved["evidence_registry"]
    before_sources = deepcopy(sources)
    generated = typed(raw(saved), sources)
    before_draft = generated.model_dump()
    result = canonical_draft(ChatDraft, generated, sources)
    for finding, expected in zip(result.answer, saved["expected_citation_coverage"], strict=True):
        assert finding.evidence_ids == expected["expected_derived_citations"]
    assert [len(finding.evidence_ids) for finding in result.answer] == [5, 6]
    assert source_id("net_income") not in result.answer[0].evidence_ids
    assert source_id("base_fair_value") not in result.answer[1].evidence_ids
    assert source_id("market_price") not in result.answer[1].evidence_ids
    assert set(validate_findings(result.answer, sources)) == set(sources)
    rendered = [render_finding(finding, sources) for finding in result.answer]
    assert [len(finding["quantitative_claims"]) for finding in rendered] == [3, 2]
    assert "$619.56" in rendered[0]["explanation"]
    assert "$539.44" in rendered[0]["explanation"]
    assert "Forward P/E" in rendered[0]["explanation"]
    assert rendered[1]["category"] == "interpretation"
    assert rendered[1]["uncertainty"] == "analytical"
    for finding in rendered:
        for claim in finding["quantitative_claims"]:
            source = sources[claim["evidence_id"]]
            assert claim == {"evidence_id": source["id"], **{key: source[key] for key in ("metric", "value", "unit", "period", "derivation")}}
    assert sources == before_sources
    assert generated.model_dump() == before_draft
    assert hashlib.sha256(saved["raw_output_text"].encode("utf-8")).hexdigest() == RAW_SHA


@pytest.mark.asyncio
async def test_exact_captured_chat_passes_real_client_sdk_and_service_using_mock_http_only():
    saved = capture()
    assembled = evidence_package()
    before = deepcopy(assembled)
    requests = []

    async def handle(request):
        body = json.loads(request.content)
        requests.append(body)
        return httpx.Response(200, json={"id": "resp_fixture", "object": "response", "created_at": 0,
            "status": "completed", "model": "test-configured-model", "error": None, "incomplete_details": None,
            "output": [{"id": "msg_fixture", "type": "message", "role": "assistant", "status": "completed",
                        "content": [{"type": "output_text", "text": saved["raw_output_text"], "annotations": []}]}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        sdk = openai.AsyncOpenAI(api_key="fake-test-key", http_client=http, max_retries=0)
        assembler = SimpleNamespace(assemble=AsyncMock(return_value=assembled))
        research = ResearchService(configured(), assembler, ResearchClient(configured(), sdk))
        try:
            answer = await research.chat("MSFT", ChatRequest(question=saved["question"]), "fixture-owner")
            ResearchAnswer.model_validate(answer)
            assert len(answer["answer"]) == 2
            assert len(answer["evidence_references"]) == 10
            assert [len(item["evidence_ids"]) for item in answer["answer"]] == [5, 6]
            assert answer["answer"][0]["quantitative_claims"][0]["value"] == 619.5604742486083
            assert answer["answer"][1]["category"] == "interpretation"
            for metric in ("total_liabilities", "net_income"):
                evidence_id = source_id(metric)
                assert research.evidence("MSFT", evidence_id, answer["snapshot_token"], "fixture-owner") == assembled["registry"][evidence_id]
                with pytest.raises(ApiError) as unauthorized:
                    research.evidence("MSFT", evidence_id, answer["snapshot_token"], "another-owner")
                assert unauthorized.value.code == "ai_evidence_not_found"
            assert sdk.max_retries == 0
        finally:
            await research.close()
    assert len(requests) == 1
    request = requests[0]
    assert request["store"] is False
    assert request["max_output_tokens"] == 5000
    assert request["tools"] == [] and request["tool_choice"] == "none"
    assert request["text"]["format"]["strict"] is True
    data = json.loads(request["input"][0]["content"])["untrusted_data"]
    assert data["question"] == saved["question"] and data["history"] == []
    assert assembled == before


def test_empty_supplemental_citations_are_supplied_by_own_typed_parts():
    original = raw()
    for finding in original["answer"]:
        finding["evidence_ids"] = []
    result = canonical(original)
    assert result.answer[0].evidence_ids == [part["evidence_id"] for part in original["answer"][0]["explanation"] if "evidence_id" in part]
    assert result.answer[1].evidence_ids == [source_id("total_liabilities"), source_id("net_income")]
    validate_findings(result.answer, registry())


def test_explicit_reuse_by_both_findings_is_allowed_but_other_citations_do_not_leak():
    original = raw()
    quote = source_id("market_price")
    original["answer"][1]["explanation"].append({"kind": "value", "evidence_id": quote})
    result = canonical(original)
    assert quote in result.answer[0].evidence_ids and quote in result.answer[1].evidence_ids
    assert source_id("base_fair_value") not in result.answer[1].evidence_ids
    assert source_id("base_model_results") not in result.answer[0].evidence_ids
    validate_findings(result.answer, registry())


def test_duplicate_declarations_and_bindings_deduplicate_sources_without_altering_parts():
    original = raw()
    original["answer"][1]["evidence_ids"].extend(original["answer"][1]["evidence_ids"])
    before = deepcopy(original)
    result = canonical(original)
    second = result.answer[1]
    assert len(second.evidence_ids) == 6
    assert second.explanation.count("{{value:" + source_id("net_income") + "}}") == 3
    assert len(render_finding(second, registry())["quantitative_claims"]) == 2
    assert original == before


@pytest.mark.parametrize("kind", ["value", "date", "period", "model"])
def test_unknown_or_out_of_request_typed_source_fails_closed(kind):
    original = raw()
    original["answer"][1]["explanation"] = [{"kind": kind, "evidence_id": "e_another_request"}]
    with pytest.raises(ApiError) as error:
        canonical_draft(ChatDraft, unchecked(original), registry())
    assert error.value.code == "unsupported_ai_binding"
    assert error.value.details["rule"] == "unknown_or_out_of_scope_typed_binding"


def test_unknown_declared_source_is_not_removed_or_repaired():
    original = raw()
    original["answer"][1]["evidence_ids"].append("e_another_request")
    with pytest.raises(ApiError) as error:
        canonical_draft(ChatDraft, unchecked(original), registry())
    assert error.value.code == "unsupported_ai_citation"


@pytest.mark.parametrize("metric", ["debt", "wacc", "base_model_results", "valuation_methodology", "base_model_name"])
def test_null_structured_narrative_and_model_name_sources_cannot_supply_values(metric):
    original = raw()
    original["answer"][1]["explanation"] = [{"kind": "value", "evidence_id": source_id(metric)}]
    with pytest.raises(ApiError) as error:
        canonical_draft(ChatDraft, unchecked(original), registry())
    assert error.value.code == "unsupported_ai_binding"
    assert error.value.details["rule"] == "ineligible_typed_binding"


@pytest.mark.parametrize("changed", [{"value": None}, {"value": True}, {"value": float("nan")},
                                      {"category": "unavailable"}, {"compatible": False}, {"scope_verified": False},
                                      {"status": "invalid_input"}, {"unit": "invented-unit"}])
def test_eligibility_is_rechecked_after_generation_parsing(changed):
    sources = registry()
    generated = typed(sources=sources)
    sources[source_id("total_liabilities")].update(changed)
    with pytest.raises(ApiError) as error:
        canonical_draft(ChatDraft, generated, sources)
    assert error.value.code == "unsupported_ai_binding"
    assert error.value.details["rule"] == "ineligible_typed_binding"


@pytest.mark.parametrize("metric,expected", [("total_liabilities", "unsupported_ai_binding"), ("base_model_results", "unsupported_ai_citation")])
def test_source_record_identity_must_match_request_registry_key(metric, expected):
    sources = registry()
    generated = typed(sources=sources)
    sources[source_id(metric)]["id"] = "e_other_record"
    with pytest.raises(ApiError) as error:
        canonical_draft(ChatDraft, generated, sources)
    assert error.value.code == expected


@pytest.mark.parametrize("part", [{"kind": "claim", "evidence_id": "e_x"},
                                  {"kind": "value", "evidence_id": "e_x", "value": 900},
                                  {"kind": "text", "text": "Plain prose", "evidence_id": "e_x"}])
def test_unknown_kind_and_extra_binding_fields_are_never_inferred(part):
    original = raw()
    original["answer"][1]["explanation"] = [part]
    with pytest.raises(ApiError) as error:
        canonical_draft(ChatDraft, unchecked(original), registry())
    assert error.value.code == "unsupported_ai_binding"


def test_raw_braced_tokens_in_text_are_rejected_instead_of_gaining_coverage():
    original = raw()
    original["answer"][1]["explanation"] = [{"kind": "text", "text": "{{value:" + source_id("market_price") + "}}"}]
    with pytest.raises(ApiError) as error:
        canonical_draft(ChatDraft, unchecked(original), registry())
    assert error.value.code == "unsupported_ai_binding"
    assert error.value.details["rule"] == "typed_text_binding_forbidden"


@pytest.mark.parametrize("text", ["Unsupported amount $999.", "Unsupported amount nine billion.", "Source e_999_global is cited implicitly."])
def test_raw_numbers_and_source_ids_in_text_never_gain_numeric_or_citation_coverage(text):
    original = raw()
    original["answer"][1]["explanation"] = [{"kind": "text", "text": text}]
    result = canonical(original)
    assert result.answer[1].evidence_ids == original["answer"][1]["evidence_ids"]
    with pytest.raises(ApiError) as error:
        validate_findings(result.answer, registry())
    assert error.value.code == "unsupported_ai_number"


def test_source_union_limit_fails_closed_without_truncation_or_mutation():
    sources = registry()
    template = sources[source_id("market_price")]
    ids = ["e_extra_" + str(index) for index in range(13)]
    sources.update({key: {**deepcopy(template), "id": key} for key in ids})
    original = raw()
    original["answer"] = [original["answer"][1]]
    original["answer"][0]["evidence_ids"] = []
    original["answer"][0]["explanation"] = [{"kind": "value", "evidence_id": key} for key in ids]
    generated = typed(original, sources)
    before = generated.model_dump()
    with pytest.raises(ApiError) as error:
        canonical_draft(ChatDraft, generated, sources)
    assert error.value.code == "ai_render_limit"
    assert generated.model_dump() == before


def test_readonly_registry_and_source_records_are_supported_without_mutation():
    sources = registry()
    before = deepcopy(sources)
    generated = typed(sources=sources)
    readonly = MappingProxyType({key: MappingProxyType(item) for key, item in sources.items()})
    result = canonical_draft(ChatDraft, generated, readonly)
    validate_findings(result.answer, readonly)
    assert sources == before


def test_text_only_finding_without_declared_or_typed_sources_remains_rejected():
    original = raw()
    original["answer"][1]["evidence_ids"] = []
    original["answer"][1]["explanation"] = [{"kind": "text", "text": "The available evidence is limited."}]
    with pytest.raises(ApiError) as error:
        canonical(original)
    assert error.value.code == "unsupported_ai_citation"


def test_policy_values_cannot_be_relabelled_as_reported_facts_after_coverage_derivation():
    original = raw()
    original["answer"][0]["category"] = "reported_fact"
    original["answer"][0]["uncertainty"] = "documented"
    result = canonical(original)
    with pytest.raises(ApiError) as error:
        validate_findings(result.answer, registry())
    assert error.value.code == "conflicting_ai_category"


@pytest.mark.parametrize("field,value", [("value", 999), ("unit", "EUR"), ("period", "FY2024"),
                                        ("metric", "invented_metric"), ("derivation", "invented calculation")])
def test_coverage_does_not_relax_exact_financial_claim_validation(field, value):
    sources = registry()
    result = canonical(sources=sources)
    item = sources[source_id("base_fair_value")]
    claim = {"evidence_id": item["id"], **{key: item[key] for key in ("metric", "value", "unit", "period", "derivation")}}
    claim[field] = value
    result.answer[0].quantitative_claims = [QuantitativeClaim.model_validate(claim)]
    with pytest.raises(ApiError) as error:
        validate_findings(result.answer, sources)
    assert error.value.code == "unsupported_ai_claim"


@pytest.mark.asyncio
async def test_client_freezes_serialized_scope_before_await_and_rejects_later_payload_injection():
    sources = registry()
    payload = {"registry": sources}
    foreign = "e_injected_after_request"
    original = raw()
    original["answer"][1]["explanation"] = [{"kind": "value", "evidence_id": foreign}]
    requests = []

    async def create(**kwargs):
        requests.append(kwargs)
        sources[foreign] = {**deepcopy(sources[source_id("market_price")]), "id": foreign}
        return SimpleNamespace(status="completed", output_text=json.dumps(original))

    sdk = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(side_effect=create)), close=AsyncMock())
    client = ResearchClient(configured(), sdk)
    with pytest.raises(ApiError) as error:
        await client.generate(ChatDraft, payload, CHAT_TASK)
    assert error.value.code == "invalid_ai_output"
    assert len(requests) == 1
    sent = json.loads(requests[0]["input"][0]["content"])["untrusted_data"]["registry"]
    assert foreign not in sent
    assert foreign in sources
    await client.close()
    sdk.close.assert_awaited_once()


def test_dynamic_generation_enums_still_reject_ineligible_values_and_unknown_ids():
    model = generation_model(ChatDraft, {"registry": registry()})
    for evidence_id in (source_id("debt"), source_id("base_model_results"), "e_another_request"):
        original = raw()
        original["answer"][1]["explanation"] = [{"kind": "value", "evidence_id": evidence_id}]
        with pytest.raises(ValidationError):
            model.model_validate(original)
