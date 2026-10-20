"""Offline classification contracts, including the partially captured MSFT failure.

The expected matrix is deliberately independent of the implementation constant.
The small JSON Schema oracle checks only the supported subset generated here;
it is not a general JSON Schema validator and introduces no runtime dependency.
"""
from copy import deepcopy
import json
import math
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.ai.client import ResearchClient
from app.ai.prompts import PROMPT_VERSION, SYSTEM_PROMPT
from app.ai.schemas import ChatDraft, ChatRequest, Finding, QuantitativeClaim, ReportDraft, ReportSections
from app.ai.validation import render_finding, validate_findings, validation_diagnostic
from app.core.exceptions import ApiError
from ai_generation_helpers import generation_json


EXPECTED = {
    "reported_fact": ("documented", "limited"),
    "historical_metric": ("documented", "analytical", "limited"),
    "valuation_output": ("analytical", "limited"),
    "policy_estimate": ("analytical", "limited"),
    "user_assumption": ("analytical", "limited"),
    "filing_excerpt": ("documented", "limited"),
    "company_profile": ("documented", "limited"),
    "interpretation": ("analytical", "limited"),
    "unavailable": ("unavailable",),
}
UNCERTAINTIES = ("documented", "analytical", "limited", "unavailable")
PAIRS = [(category, uncertainty) for category in EXPECTED for uncertainty in UNCERTAINTIES]
FINDING_FIELDS = {"title", "explanation", "evidence_ids", "category", "uncertainty", "quantitative_claims"}
FIXTURE = Path(__file__).parent / "fixtures" / "ai" / "msft_category_uncertainty_failure.json"


def payload(category="interpretation", uncertainty="limited", **changes):
    return {
        "title": "Source interpretation",
        "explanation": "The supplied source retains its stated scope and limitations.",
        "evidence_ids": ["e_source"],
        "category": category,
        "uncertainty": uncertainty,
        "quantitative_claims": [],
        **changes,
    }


def source_registry(category):
    item = {
        "id": "e_source", "category": "historical_metric" if category == "interpretation" else category,
        "provider": "Deterministic offline fixture", "title": "Source record", "ticker": "MSFT",
        "metric": "source_record", "value": None if category == "unavailable" else "Recorded source information.",
        "unit": "text", "period": None, "observation_date": None, "retrieved_at": None,
        "source_url": None, "accession": None, "derivation": None, "quality_warnings": [], "excerpt": None,
    }
    return {item["id"]: item}


def _resolve(schema, root):
    reference = schema["$ref"]
    assert reference.startswith("#/")
    target = root
    for part in reference[2:].split("/"):
        target = target[part.replace("~1", "/").replace("~0", "~")]
    return target


def _accepts(schema, value, root):
    """Evaluate the generated reference/object/array/enum/anyOf subset."""
    if "$ref" in schema:
        return _accepts(_resolve(schema, root), value, root)
    if "anyOf" in schema and not any(_accepts(branch, value, root) for branch in schema["anyOf"]):
        return False
    if "enum" in schema and value not in schema["enum"]:
        return False
    kind = schema.get("type")
    if kind == "object":
        if not isinstance(value, dict) or set(schema.get("required", [])) - value.keys():
            return False
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False and value.keys() - properties.keys():
            return False
        return all(_accepts(properties[key], item, root) for key, item in value.items() if key in properties)
    if kind == "array":
        return (isinstance(value, list)
                and schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", math.inf)
                and all(_accepts(schema["items"], item, root) for item in value))
    if kind == "string":
        return isinstance(value, str) and schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", math.inf)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    if kind == "null":
        return value is None
    assert kind is None, f"Unsupported oracle type: {kind}"
    return True


def _model_payloads(finding):
    return (
        (Finding, finding),
        (ChatDraft, {"answer": [finding]}),
        (ReportDraft, {"sections": {section: [finding] for section in ReportSections.model_fields}}),
    )


@pytest.mark.parametrize("category,uncertainty", PAIRS)
def test_complete_category_uncertainty_matrix_agrees_across_runtime_json_and_generated_schema(category, uncertainty):
    allowed = uncertainty in EXPECTED[category]
    finding = payload(category, uncertainty)
    for model, body in _model_payloads(finding):
        schema = model.model_json_schema()
        assert _accepts(schema, body, schema) is allowed
        if allowed:
            assert model.model_validate(body).model_dump() == body
            assert model.model_validate_json(json.dumps(body)).model_dump() == body
        else:
            with pytest.raises(ValidationError):
                model.model_validate(body)
            with pytest.raises(ValidationError):
                model.model_validate_json(json.dumps(body))


@pytest.mark.parametrize("category,uncertainty", PAIRS)
def test_server_guard_also_enforces_matrix_when_construction_or_mutation_bypasses_pydantic(category, uncertainty):
    items = source_registry(category)
    body = payload(category, uncertainty)
    constructed = Finding.model_construct(**body)
    mutated = Finding(**payload(category, EXPECTED[category][0]))
    mutated.uncertainty = uncertainty
    for candidate in (constructed, mutated):
        if uncertainty in EXPECTED[category]:
            assert validate_findings([candidate], items) == ["e_source"]
        else:
            with pytest.raises(ApiError) as rejected:
                validate_findings([candidate], items)
            assert rejected.value.code == "conflicting_ai_category"
            assert rejected.value.details == {
                "rule": "category_uncertainty_mismatch", "finding_category": category,
                "finding_uncertainty": uncertainty, "allowed_uncertainties": list(EXPECTED[category]),
            }


@pytest.mark.parametrize("model", [ChatDraft, ReportDraft])
def test_request_schema_uses_nested_strict_objects_and_supported_anyof_without_conditionals(model):
    schema = model.model_json_schema()
    assert schema["type"] == "object" and "anyOf" not in schema
    finding_schema = schema["$defs"]["Finding"]
    assert "anyOf" in finding_schema and "properties" not in finding_schema
    assert set().union(*(set(branch["properties"]["category"]["enum"]) for branch in finding_schema["anyOf"])) == set(EXPECTED)
    forbidden = {"oneOf", "allOf", "discriminator", "if", "then", "else", "not", "dependentSchemas", "dependentRequired"}

    def inspect(node):
        assert not forbidden.intersection(node)
        if "$ref" in node:
            assert isinstance(_resolve(node, schema), dict)
        if node.get("type") == "object":
            assert node.get("additionalProperties") is False
            assert set(node["required"]) == set(node["properties"])
        for mapping in ("$defs", "properties"):
            for child in node.get(mapping, {}).values():
                inspect(child)
        for child in node.get("anyOf", []):
            inspect(child)
        if "items" in node:
            inspect(node["items"])

    inspect(schema)
    for branch in finding_schema["anyOf"]:
        assert set(branch["properties"]) == FINDING_FIELDS
        assert set(branch["required"]) == FINDING_FIELDS


@pytest.mark.parametrize("model", [ChatDraft, ReportDraft])
@pytest.mark.parametrize("change", ["missing_uncertainty", "extra_field", "unknown_category", "unknown_uncertainty"])
def test_strict_nested_branch_cannot_accept_missing_extra_or_unknown_classification_fields(model, change):
    finding = payload()
    if change == "missing_uncertainty":
        finding.pop("uncertainty")
    elif change == "extra_field":
        finding["trusted"] = True
    elif change == "unknown_category":
        finding["category"] = "audited_truth"
    else:
        finding["uncertainty"] = "certain"
    body = dict(_model_payloads(finding))[model]
    schema = model.model_json_schema()
    assert not _accepts(schema, body, schema)
    with pytest.raises(ValidationError):
        model.model_validate_json(json.dumps(body))


def captured_failure():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def synthetic_methodology_finding(uncertainty):
    """Reconstruct only known labels/source; this prose was never captured live."""
    captured = captured_failure()
    partial = captured["error"]["details"]["evidence"][0]
    item = {**source_registry("historical_metric")["e_source"], **partial, "category": "historical_metric"}
    synthetic = payload("interpretation", uncertainty, title="Synthetic methodology interpretation",
                        explanation="The supplied methodology describes separate cash flow and discount rate requirements. This explanation is an analytical interpretation of that methodology.",
                        evidence_ids=[item["id"]])
    return synthetic, {item["id"]: item}


def test_partial_live_fixture_records_labels_and_limitations_without_fabricating_the_lost_answer():
    fixture = captured_failure()
    assert fixture["fixture_type"] == "sanitized_partial_live_failure_record"
    assert fixture["question"] == "Why is MSFT's valuation available or unavailable?"
    assert fixture["rejected_finding_labels"]["category"] == "interpretation"
    assert fixture["rejected_finding_labels"]["uncertainty"] == "documented"
    assert fixture["error"]["details"]["finding_index"] == 1
    assert fixture["error"]["details"]["evidence"][0]["metric"] == "valuation_methodology"
    assert any("not retained" in note for note in fixture["capture_limitations"])
    assert not {"title", "explanation", "answer", "quantitative_claims"}.intersection(fixture)
    assert set(fixture["rejected_finding_labels"]) == {"category", "uncertainty", "provenance"}


def test_synthetic_reconstruction_of_captured_invalid_pair_stays_rejected_and_diagnostic_is_exact():
    body, items = synthetic_methodology_finding("documented")
    with pytest.raises(ValidationError):
        Finding.model_validate(body)
    candidate = Finding.model_construct(**body)
    original = deepcopy(body)
    with pytest.raises(ApiError):
        render_finding(candidate, items)
    diagnostic = validation_diagnostic([candidate], items)
    assert diagnostic["rule"] == "category_uncertainty_mismatch"
    assert diagnostic["finding_category"] == "interpretation"
    assert diagnostic["finding_uncertainty"] == "documented"
    assert diagnostic["allowed_uncertainties"] == ["analytical", "limited"]
    assert diagnostic["field"] == "uncertainty" and diagnostic["rejected_span"] == "documented"
    assert candidate.model_dump() == original


@pytest.mark.parametrize("uncertainty", ["analytical", "limited"])
def test_corrected_synthetic_methodology_pair_remains_an_interpretation_not_a_fact(uncertainty):
    body, items = synthetic_methodology_finding(uncertainty)
    candidate = Finding.model_validate(body)
    rendered = render_finding(candidate, items)
    assert rendered["category"] == "interpretation"
    assert rendered["uncertainty"] == uncertainty
    assert rendered["quantitative_claims"] == []
    assert rendered["evidence_ids"] == body["evidence_ids"]
    assert candidate.model_dump() == body


@pytest.mark.parametrize("field,wrong", [
    ("value", 619.56), ("metric", "invented_metric"), ("unit", "EUR/share"),
    ("period", "FY2024"), ("derivation", "Invented AI calculation"),
])
def test_valid_classification_does_not_relax_exact_numeric_evidence_checks(field, wrong):
    from test_ai_numeric_audit import claim, registry

    items = registry()
    quantity = claim(items["e_fair"]).model_dump()
    quantity[field] = wrong
    candidate = Finding(**payload(explanation="The registered estimate retains its source basis.",
                                  evidence_ids=["e_fair"], quantitative_claims=[QuantitativeClaim(**quantity)]))
    with pytest.raises(ApiError) as rejected:
        validate_findings([candidate], items)
    assert rejected.value.code == "unsupported_ai_claim"


@pytest.mark.parametrize("case,code", [
    ("raw_number", "unsupported_ai_number"),
    ("unknown_citation", "unsupported_ai_citation"),
    ("uncited_binding", "unsupported_ai_binding"),
    ("policy_as_fact", "conflicting_ai_category"),
])
def test_valid_classification_does_not_legitimize_numbers_or_citations(case, code):
    from test_ai_numeric_audit import registry

    items = registry()
    body = payload(evidence_ids=["e_fair"])
    if case == "raw_number":
        body["explanation"] = "The fair value is $999 billion."
    elif case == "unknown_citation":
        body["evidence_ids"] = ["e_invented"]
    elif case == "uncited_binding":
        body["explanation"] = "The quote is {{value:e_price}}."
    else:
        body.update(category="reported_fact", uncertainty="documented", explanation="The reported value is {{value:e_fair}}.")
    candidate = Finding.model_validate(body)
    with pytest.raises(ApiError) as rejected:
        render_finding(candidate, items)
    assert rejected.value.code == code


@pytest.mark.asyncio
@pytest.mark.parametrize("uncertainty", ["analytical", "limited", "documented"])
async def test_exact_msft_question_with_valuation_and_methodology_through_mocked_sdk(uncertainty):
    from test_ai_numeric_audit import registry
    from test_ai_research_service import package, service

    question = "Why is MSFT's valuation available or unavailable?"
    methodology, method_items = synthetic_methodology_finding(uncertainty)
    valuation = payload("valuation_output", "analytical", title="Illustrative valuation availability",
                        explanation="The policy-based {{model:e_model}} estimate is {{value:e_fair}}, versus {{value:e_price}} observed on {{date:e_price}}. Only {{value:e_count}} model contributes; low quality and missing independent confirmation remain limitations.",
                        evidence_ids=["e_fair", "e_price", "e_count", "e_model"])
    raw_draft = {"answer": [valuation, methodology]}
    sdk = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(return_value=SimpleNamespace(
        status="completed", output_text=generation_json(raw_draft)))), close=AsyncMock())
    research = service()
    research.client = ResearchClient(research.settings, sdk=sdk)
    context = package(ticker="MSFT")
    context["registry"] = {**registry(), **method_items}
    original = deepcopy(context)
    research.assembler.assemble.return_value = context
    try:
        if uncertainty == "documented":
            with pytest.raises(ApiError) as rejected:
                await research.chat("MSFT", ChatRequest(question=question), "offline-classification-review")
            assert rejected.value.code == "conflicting_ai_category"
            assert rejected.value.details == {
                "rule": "category_uncertainty_mismatch", "field": ["answer", 1],
                "finding_category": "interpretation", "finding_uncertainty": "documented",
                "allowed_uncertainties": ["analytical", "limited"],
            }
            assert not research.snapshots and not research.reports
        else:
            result = await research.chat("MSFT", ChatRequest(question=question), "offline-classification-review")
            valuation_result, methodology_result = result["answer"]
            assert valuation_result["category"] == "policy_estimate" and valuation_result["uncertainty"] == "limited"
            assert "$619.56" in valuation_result["explanation"] and "$533.69" in valuation_result["explanation"]
            assert "Only 1 model contributes" in valuation_result["explanation"]
            assert "2026-10-14" in valuation_result["explanation"]
            assert methodology_result["category"] == "interpretation" and methodology_result["uncertainty"] == uncertainty
            sources = {item["id"]: item for item in result["evidence_references"]}
            for finding in result["answer"]:
                assert set(finding["evidence_ids"]) <= sources.keys()
                for quantity in finding["quantitative_claims"]:
                    assert all(quantity[field] == sources[quantity["evidence_id"]].get(field)
                               for field in ("metric", "value", "unit", "period", "derivation"))
        sdk.responses.create.assert_awaited_once()
        arguments = sdk.responses.create.call_args.kwargs
        assert arguments["store"] is False and arguments["tools"] == []
        assert arguments["text"]["format"]["strict"] is True
        assert arguments["instructions"] == SYSTEM_PROMPT
        request = json.loads(arguments["input"][0]["content"])["untrusted_data"]
        assert request["question"] == question and request["history"] == []
        assert research.assembler.assemble.return_value == original
    finally:
        await research.close()
        sdk.close.assert_awaited_once()


def test_prompt_states_complete_pair_contract_and_does_not_call_interpretation_documented():
    assert PROMPT_VERSION != "fairworth-research-5"
    for category, uncertainties in EXPECTED.items():
        assert f"- {category}: {' or '.join(uncertainties)}" in SYSTEM_PROMPT
    assert "Never emit interpretation with documented uncertainty" in SYSTEM_PROMPT


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["invalid_pair", "unknown_enum"])
async def test_sdk_parser_diagnostics_never_expose_private_prose_or_pydantic_raw_input(failure):
    from test_ai_research_service import configured

    private = "private_offline_parser_marker"
    finding = payload("interpretation", "documented", title=f"Source annotation {private}",
                      explanation=f"Untrusted source text contains {private} and analyst@example.com.")
    if failure == "unknown_enum":
        finding["category"] = private
    raw = {"answer": [finding]}
    sdk = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(return_value=SimpleNamespace(
        status="completed", output_text=generation_json(raw)))), close=AsyncMock())
    client = ResearchClient(configured(), sdk=sdk)
    try:
        with pytest.raises(ApiError) as rejected:
            await client.generate(ChatDraft, {"registry": source_registry("historical_metric")}, "Offline parser audit")
        error = rejected.value
        serialized = json.dumps({"code": error.code, "message": error.message, "details": error.details})
        assert private not in serialized and "analyst@example.com" not in serialized
        assert "Source annotation" not in serialized and "Untrusted source text" not in serialized
        if failure == "invalid_pair":
            assert error.code == "conflicting_ai_category"
            assert error.details == {
                "rule": "category_uncertainty_mismatch", "field": ["answer", 0],
                "finding_category": "interpretation", "finding_uncertainty": "documented",
                "allowed_uncertainties": ["analytical", "limited"],
            }
        else:
            assert error.code == "invalid_ai_output" and error.details is None
        sdk.responses.create.assert_awaited_once()
    finally:
        await client.close()
        sdk.close.assert_awaited_once()
