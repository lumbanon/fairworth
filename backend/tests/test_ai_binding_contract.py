"""Captured v6 failures and v7 typed bindings, strictly offline through the SDK."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.ai.bindings import binding_catalog, canonical_draft, generation_model
from app.ai.client import ResearchClient, input_size
from app.ai.prompts import CHAT_TASK, PROMPT_VERSION
from app.ai.schemas import ChatDraft, ChatRequest, Finding, ReportDraft
from app.ai.validation import render_finding, validate_findings, validation_diagnostic
from app.core.exceptions import ApiError
from test_ai_classification import EXPECTED, PAIRS, _accepts, _resolve
from test_ai_research_service import configured, package, service


FIXTURE = Path(__file__).parent / "fixtures" / "ai" / "msft_v6_binding_failure.json"


def captured():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def context():
    result = package(ticker="MSFT")
    result["registry"] = captured()["evidence_registry"]
    result["binding_catalog"] = binding_catalog(result["registry"])
    return result


def source(metric):
    return next(item for item in context()["registry"].values() if item["metric"] == metric)


def typed_finding(explanation=None, **changes):
    fair, price, count, model = [source(metric)["id"] for metric in (
        "base_fair_value", "market_price", "base_contributing_model_count", "base_model_name")]
    return {"title": "Illustrative valuation availability",
        "explanation": explanation or [
            {"kind": "text", "text": "The policy-based "},
            {"kind": "model", "evidence_id": model},
            {"kind": "text", "text": " estimate is "},
            {"kind": "value", "evidence_id": fair},
            {"kind": "text", "text": ", versus a dated market price of "},
            {"kind": "value", "evidence_id": price},
            {"kind": "text", "text": " observed on "},
            {"kind": "date", "evidence_id": price},
            {"kind": "text", "text": ". Only "},
            {"kind": "value", "evidence_id": count},
            {"kind": "text", "text": " model contributes; low valuation quality and missing independent confirmation remain limitations. Missing debt and WACC prevent unsupported DCF models from becoming available."}],
        "evidence_ids": [fair, price, count, model], "category": "interpretation",
        "uncertainty": "limited", "quantitative_claims": [], **changes}


def test_captured_failure_is_exact_retained_output_not_a_reconstruction():
    fixture = captured()
    assert fixture["question"] == "Why is MSFT's valuation available or unavailable?"
    assert hashlib.sha256(fixture["raw_output_text"].encode()).hexdigest() == fixture["capture_provenance"]["original_text_sha256"]
    draft = ChatDraft.model_validate_json(fixture["raw_output_text"])
    assert len(draft.answer[0].title) == 160
    assert draft.answer[0].title.endswith("{{date:e_c667a7d34c")
    assert "Only one model" in draft.answer[0].explanation
    diagnostic = validation_diagnostic(draft.answer, fixture["evidence_registry"])
    assert diagnostic["error_code"] == "unsupported_ai_binding"
    assert diagnostic["rule"] == "malformed_binding"
    assert diagnostic["field"] == "title"
    assert diagnostic["rejected_span"] == "{{date:e_c667a7d34c"
    assert diagnostic["rejected_span"] != "667"


@pytest.mark.parametrize("metric", ["debt", "wacc", "base_model_results", "confidence", "valuation_methodology"])
def test_each_captured_non_scalar_or_null_reference_fails_independently(metric):
    fixture = captured()
    item = source(metric)
    text = "The referenced source value is {{value:" + item["id"] + "}}."
    assert "{{value:" + item["id"] + "}}" in fixture["raw_output_text"]
    candidate = Finding(title="Source limitation", explanation=text, evidence_ids=[item["id"]],
                        category="interpretation", uncertainty="limited", quantitative_claims=[])
    with pytest.raises(ApiError) as rejected:
        render_finding(candidate, fixture["evidence_registry"])
    assert rejected.value.code == "unsupported_ai_binding"
    diagnostic = validation_diagnostic([candidate], fixture["evidence_registry"])
    assert diagnostic["rule"] == "ineligible_binding"
    assert diagnostic["evidence_id"] == item["id"]
    assert diagnostic["rejected_span"] == "{{value:" + item["id"] + "}}"
    model = generation_model(ChatDraft, context())
    with pytest.raises(ValidationError):
        model.model_validate({"answer": [typed_finding(
            explanation=[{"kind": "value", "evidence_id": item["id"]}], evidence_ids=[item["id"]])]})


@pytest.mark.parametrize("fragment", ["{{date:e_c667a7d34c", "{{value:e_08a38cfcbd0ebf8f7e26541857636ba7}", "{value:e_id}"])
def test_incomplete_or_raw_tokens_are_never_truncated_or_rendered(fragment):
    candidate = Finding(title="Source limitation", explanation="Dated source " + fragment,
        evidence_ids=[source("market_price")["id"]], category="interpretation", uncertainty="limited", quantitative_claims=[])
    original = candidate.model_dump()
    diagnostic = validation_diagnostic([candidate], context()["registry"])
    assert diagnostic["rule"] == "malformed_binding"
    assert diagnostic["field"] == "explanation" and diagnostic["rejected_span"] == fragment
    assert candidate.model_dump() == original
    with pytest.raises(ValidationError):
        generation_model(ChatDraft, context()).model_validate({"answer": [typed_finding(
            explanation=[{"kind": "text", "text": "Dated source " + fragment}])]})


@pytest.mark.parametrize("text", ["Only one model contributes.", "The estimate is $619.56.",
    "The source period is FY2026.", "The quote date is 2026-10-15.", "The policy rate is ten percent.",
    "Revenue was 10K.", "Revenue was 10Q.", "Revenue was 10-K."])
def test_ordinary_numeric_prose_still_fails_after_structured_references_pass(text):
    model = generation_model(ChatDraft, context())
    draft = canonical_draft(ChatDraft, model.model_validate({"answer": [typed_finding(
        explanation=[{"kind": "text", "text": text}])]}), context()["registry"])
    with pytest.raises(ApiError) as rejected:
        validate_findings(draft.answer, context()["registry"])
    assert rejected.value.code == "unsupported_ai_number"


@pytest.mark.parametrize("parts,code", [
    (["Only on", "e model contributes."], "unsupported_ai_number"),
    (["See htt", "ps://example.com"], "unsafe_ai_output"),
    (["The stock is a b", "uy"], "unsupported_ai_recommendation"),
])
def test_adjacent_text_segments_are_checked_as_complete_prose(parts, code):
    model = generation_model(ChatDraft, context())
    draft = canonical_draft(ChatDraft, model.model_validate({"answer": [typed_finding(
        explanation=[{"kind": "text", "text": text} for text in parts])]}), context()["registry"])
    with pytest.raises(ApiError) as rejected:
        validate_findings(draft.answer, context()["registry"])
    assert rejected.value.code == code


@pytest.mark.parametrize("category,uncertainty", PAIRS)
def test_request_scoped_schema_preserves_complete_category_matrix(category, uncertainty):
    body = {"answer": [typed_finding(category=category, uncertainty=uncertainty)]}
    model = generation_model(ChatDraft, context())
    schema = model.model_json_schema()
    allowed = uncertainty in EXPECTED[category]
    assert _accepts(schema, body, schema) is allowed
    if allowed:
        model.model_validate(body)
    else:
        with pytest.raises(ValidationError):
            model.model_validate(body)


@pytest.mark.parametrize("schema", [ChatDraft, ReportDraft])
def test_dynamic_schema_supported_subset_enums_are_shared_and_bounded(schema):
    # Worst-case 180 value/date/period records. Citation IDs must not be copied
    # across the four classification branches or the API enum limit is exceeded.
    base = source("market_price")
    registry = {"e_" + str(index): {**base, "id": "e_" + str(index), "period": "FY2026"} for index in range(180)}
    package = {"registry": registry}
    body = generation_model(schema, package).model_json_schema()
    forbidden = {"oneOf", "allOf", "discriminator", "if", "then", "else", "not", "dependentSchemas", "dependentRequired"}
    enum_count, property_count, strings, depth = 0, 0, 0, 0

    def inspect(node, level=0):
        nonlocal enum_count, property_count, strings, depth
        assert not forbidden.intersection(node)
        depth = max(depth, level)
        enum_count += len(node.get("enum", []))
        strings += sum(len(value) for value in node.get("enum", []) if isinstance(value, str))
        if "$ref" in node:
            assert isinstance(_resolve(node, body), dict)
        if node.get("type") == "object":
            assert node.get("additionalProperties") is False
            assert set(node["required"]) == set(node["properties"])
            property_count += len(node["properties"])
        for name in ("$defs", "properties"):
            for child in node.get(name, {}).values():
                inspect(child, level + 1)
        for child in node.get("anyOf", []):
            inspect(child, level + 1)
        if "items" in node:
            inspect(node["items"], level + 1)

    inspect(body)
    assert enum_count <= 1000 and property_count <= 5000 and strings <= 120000 and depth <= 10
    assert body["$defs"]["ResearchEvidenceId"]["enum"] == list(registry)
    assert json.dumps(body).count('"e_179"') == 4  # citation/value/date/period only, once each


def test_empty_binding_groups_do_not_emit_empty_enums_or_permit_text_as_values():
    method = source("valuation_methodology")
    model = generation_model(ChatDraft, {"registry": {method["id"]: method}})
    assert "ResearchValue" not in model.model_json_schema()["$defs"]
    with pytest.raises(ValidationError):
        model.model_validate({"answer": [typed_finding(evidence_ids=[method["id"]],
            explanation=[{"kind": "value", "evidence_id": method["id"]}])]})


@pytest.mark.asyncio
async def test_exact_msft_question_through_mocked_sdk_passes_every_independent_validator():
    research = service()
    research.assembler.assemble.return_value = context()
    method = source("valuation_methodology")["id"]
    raw = {"answer": [typed_finding(), typed_finding(title="Methodology and missing evidence",
        explanation=[{"kind": "text", "text": "The supplied methodology describes distinct cash flow and discount rate requirements. Missing debt and WACC remain unavailable; chat cannot substitute assumptions or change model eligibility."}],
        evidence_ids=[method], category="interpretation", uncertainty="analytical")]}
    sdk = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(return_value=SimpleNamespace(
        status="completed", output_text=json.dumps(raw)))), close=AsyncMock())
    research.client = ResearchClient(research.settings, sdk=sdk)
    before = deepcopy(research.assembler.assemble.return_value)
    result = await research.chat("MSFT", ChatRequest(question=captured()["question"]), "offline-binding-review")
    sdk.responses.create.assert_awaited_once()
    assert PROMPT_VERSION == "fairworth-research-10"
    first = result["answer"][0]
    assert "$619.56" in first["explanation"] and "$539.44" in first["explanation"]
    assert "2026-10-15" in first["explanation"] and "Only 1 model contributes" in first["explanation"]
    assert "low valuation quality" in first["explanation"] and "{{" not in json.dumps(result)
    sources = {item["id"]: item for item in result["evidence_references"]}
    for finding in result["answer"]:
        assert set(finding["evidence_ids"]) <= sources.keys()
        for quantity in finding["quantitative_claims"]:
            assert all(quantity[key] == sources[quantity["evidence_id"]].get(key)
                       for key in ("value", "metric", "unit", "period", "derivation"))
    assert first["quantitative_claims"][0]["value"] == 619.5604742486083
    assert research.assembler.assemble.return_value == before
    sent = json.loads(sdk.responses.create.call_args.kwargs["input"][0]["content"])["untrusted_data"]
    assert sent["question"] == captured()["question"] and sent["history"] == []
    assert sent["evidence"]["binding_catalog"] == binding_catalog(sent["evidence"]["registry"])
    assert not research.reports


@pytest.mark.asyncio
@pytest.mark.parametrize("failure,code", [
    ("private", "unsafe_ai_output"), ("category", "conflicting_ai_category"), ("unknown_id", "invalid_ai_output")])
async def test_valid_typed_numerics_do_not_bypass_citations_privacy_or_categories(failure, code):
    research = service()
    research.assembler.assemble.return_value = context()
    finding = typed_finding()
    if failure == "private":
        finding["explanation"].append({"kind": "text", "text": " Contact analyst@example.com."})
    elif failure == "category":
        finding.update(category="reported_fact", uncertainty="documented")
    else:
        finding["explanation"][1]["evidence_id"] = "e_unregistered"
    sdk = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(return_value=SimpleNamespace(
        status="completed", output_text=json.dumps({"answer": [finding]})))), close=AsyncMock())
    research.client = ResearchClient(configured(), sdk=sdk)
    with pytest.raises(ApiError) as rejected:
        await research.chat("MSFT", ChatRequest(question=captured()["question"]), "offline-rejected")
    assert rejected.value.code == code
    assert not research.snapshots and not research.reports
    sdk.responses.create.assert_awaited_once()


def test_generation_and_render_limits_fail_closed_without_clipping_complete_references():
    model = generation_model(ChatDraft, context())
    with pytest.raises(ValidationError):
        model.model_validate({"answer": [typed_finding(title="x" * 161)]})
    with pytest.raises(ValidationError):
        model.model_validate({"answer": [typed_finding(explanation=[{"kind": "text", "text": "x" * 801}])]})
    # Each input segment is legal, but the final response length is authoritative.
    typed = model.model_validate({"answer": [typed_finding(explanation=[
        {"kind": "text", "text": "x" * 800}, {"kind": "text", "text": "x" * 800},
        {"kind": "value", "evidence_id": source("base_fair_value")["id"]}])]})
    with pytest.raises(ValidationError):
        canonical_draft(ChatDraft, typed, context()["registry"])


def test_full_request_budget_counts_dynamic_schema_and_catalog_not_a_static_schema():
    payload = {"evidence": context(), "question": captured()["question"], "history": []}
    from app.ai.prompts import SYSTEM_PROMPT
    expected = len((SYSTEM_PROMPT + json.dumps({"task": CHAT_TASK, "untrusted_data": payload},
        ensure_ascii=False, separators=(",", ":")) + json.dumps(generation_model(ChatDraft, payload).model_json_schema())).encode())
    assert input_size(ChatDraft, payload, CHAT_TASK) == expected
