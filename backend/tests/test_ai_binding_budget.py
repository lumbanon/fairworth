"""Request-scoped binding schemas stay bounded without losing source authority."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.ai.bindings import binding_catalog, generation_model
from app.ai.client import ResearchClient, input_size
from app.ai.prompts import CHAT_TASK, REPORT_TASK, SYSTEM_PROMPT
from app.ai.report_service import ResearchService
from app.ai.schemas import ChatDraft, ChatRequest, ReportDraft, ReportRequest
from app.core.exceptions import ApiError


CRITICAL = {
    "company_profile", "valuation_methodology", "market_price", "base_fair_value",
    "base_contributing_model_count", "base_model_name", "forward_eps", "target_pe",
    "base_model_results", "debt", "wacc", "total_debt",
}
FIXTURE = Path(__file__).parent / "fixtures" / "ai" / "msft_v6_binding_failure.json"


def actual_request_bytes(schema, payload, task):
    content = json.dumps({"task": task, "untrusted_data": payload}, ensure_ascii=False, separators=(",", ":"))
    sent_schema = generation_model(schema, payload).model_json_schema()
    return len((SYSTEM_PROMPT + content + json.dumps(sent_schema)).encode("utf-8"))


def request_payload(schema, package):
    if schema is ReportDraft:
        return package, REPORT_TASK
    return {"evidence": package, "question": f"Why is {package['ticker']}'s valuation available or unavailable?", "history": []}, CHAT_TASK


@pytest.mark.asyncio
@pytest.mark.parametrize("ticker", ["AAPL", "MSFT", "NVDA", "ORCL"])
@pytest.mark.parametrize("schema", [ReportDraft, ChatDraft])
@pytest.mark.parametrize("budget", [64000, 24000])
async def test_dynamic_request_budget_preserves_critical_evidence_or_fails_closed_without_mutating_assembler(ticker, schema, budget):
    from test_ai_four_company import research

    service, financials = research(ticker)
    original_financials = deepcopy(financials.data)
    owned_package = await service._context(ticker, None)
    original_package = deepcopy(owned_package)
    service.assembler = SimpleNamespace(assemble=AsyncMock(return_value=owned_package))
    service.settings.ai_max_context_tokens = budget
    try:
        package = await service._context(ticker, None)
        payload, task = request_payload(schema, package)
        original_records = deepcopy(package["registry"])
        before_size = actual_request_bytes(schema, payload, task)
        try:
            service._fit_context(schema, payload, task)
        except ApiError as error:
            assert budget == 24000 and error.code == "ai_context_too_large"
            assert error.status_code == 422
        else:
            size = actual_request_bytes(schema, payload, task)
            assert size == input_size(schema, payload, task) <= budget
            assert package["binding_catalog"] == binding_catalog(package["registry"])
            for identifier, record in original_records.items():
                if record["metric"] in CRITICAL:
                    assert package["registry"][identifier] == record
            for identifier, record in package["registry"].items():
                # Compare complete records, including exact values, units,
                # periods, dates, source URLs, accessions and warnings.
                assert record == original_records[identifier]
            assert {"base_model_results", "debt", "wacc", "total_debt"} <= {
                item["metric"] for item in package["registry"].values()
            }
            if before_size > budget:
                assert len(package["registry"]) < len(original_records)
                assert any("omitted records" in note for note in package["limitations"])
        assert service.settings.ai_max_context_tokens == budget
        assert service.client.inputs == []
        assert owned_package == original_package
        assert financials.data == original_financials
    finally:
        await service.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("schema", [ReportDraft, ChatDraft])
async def test_untrimmable_protected_diagnostics_fail_before_sdk_at_minimum_budget(schema):
    from test_ai_four_company import research
    from test_ai_research_service import configured

    original_service, _financials = research("MSFT")
    try:
        package = await original_service._context("MSFT", None)
    finally:
        await original_service.close()
    model_results = next(item for item in package["registry"].values() if item["metric"] == "base_model_results")
    # Synthetic long source diagnostics stress the byte bound without changing
    # an actual financial value or permitting a protected record to be clipped.
    model_results["quality_warnings"].append("Retained offline diagnostic annotation. " * 1000)
    original = deepcopy(package)
    settings = configured(ai_max_context_tokens=24000)
    sdk = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock()), close=AsyncMock())
    service = ResearchService(settings, SimpleNamespace(assemble=AsyncMock(return_value=package)), ResearchClient(settings, sdk=sdk))
    try:
        with pytest.raises(ApiError) as rejected:
            if schema is ReportDraft:
                await service.report("MSFT", ReportRequest(), "offline-budget-owner")
            else:
                await service.chat("MSFT", ChatRequest(question="Why is MSFT's valuation available or unavailable?"), "offline-budget-owner")
        assert rejected.value.code == "ai_context_too_large" and rejected.value.status_code == 422
        sdk.responses.create.assert_not_awaited()
        assert settings.ai_max_context_tokens == 24000
        assert not service.reports and not service.snapshots
        assert package == original
    finally:
        await service.close()
        sdk.close.assert_awaited_once()


def registry_record(identifier="e_source"):
    return {
        "id": identifier, "category": "reported_fact", "provider": "Deterministic offline source",
        "title": "Reported source", "ticker": "MSFT", "metric": "revenue", "value": 100,
        "unit": "USD", "period": "FY2026", "observation_date": "2026-06-30", "retrieved_at": None,
        "source_url": None, "accession": None, "derivation": None, "quality_warnings": [], "excerpt": None,
    }


@pytest.mark.parametrize("count", [1, 180, 181])
def test_dynamic_schema_accepts_supported_record_count_including_added_methodology(count):
    registry = {f"e_{index}": registry_record(f"e_{index}") for index in range(count)}
    schema = generation_model(ChatDraft, {"registry": registry}).model_json_schema()
    assert schema["type"] == "object"
    assert allowed_ids(schema["$defs"]["ResearchEvidenceId"]) == set(registry)


def test_dynamic_schema_rejects_record_count_above_supported_cap():
    registry = {f"e_{index}": registry_record(f"e_{index}") for index in range(182)}
    with pytest.raises(ApiError) as rejected:
        generation_model(ChatDraft, {"registry": registry})
    assert rejected.value.code == "ai_context_too_large" and rejected.value.status_code == 422


@pytest.mark.parametrize("identifier", ["e_source", "e_A-0", "e" * 100])
def test_dynamic_schema_accepts_ascii_evidence_ids_at_allowed_bounds(identifier):
    assert generation_model(ChatDraft, {"registry": {identifier: registry_record(identifier)}}).model_json_schema()["type"] == "object"


@pytest.mark.parametrize("identifier", ["", "e" * 101, "e_has space", "e_\uff10", "e_/../", 123])
def test_dynamic_schema_rejects_invalid_or_overlong_evidence_ids(identifier):
    with pytest.raises(ApiError) as rejected:
        generation_model(ChatDraft, {"registry": {identifier: registry_record(identifier)}})
    assert rejected.value.code == "ai_context_too_large" and rejected.value.status_code == 422


def allowed_ids(schema):
    return set(schema["enum"]) if "enum" in schema else {schema["const"]}


def test_numeric_id_enums_exclude_captured_null_structured_and_methodology_values_but_citations_retain_them():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    registry = fixture["evidence_registry"]
    original = deepcopy(registry)
    schema = generation_model(ChatDraft, {"registry": registry}).model_json_schema()
    numeric = allowed_ids(schema["$defs"]["ResearchValue"]["properties"]["evidence_id"])
    citations = allowed_ids(schema["$defs"]["ResearchEvidenceId"])
    rejected_metrics = {"debt", "wacc", "base_model_results", "confidence", "valuation_methodology"}
    for identifier, item in registry.items():
        if item["metric"] in rejected_metrics:
            assert identifier not in numeric
        if item["metric"] in {"base_fair_value", "market_price", "base_contributing_model_count"}:
            assert identifier in numeric
    assert citations == set(registry)
    assert registry == original
    for kind in ("value", "date", "period", "model"):
        name = "Research" + kind.capitalize()
        expected = set(binding_catalog(registry)[kind])
        if expected:
            assert allowed_ids(schema["$defs"][name]["properties"]["evidence_id"]) == expected
        else:
            assert name not in schema["$defs"]
