"""Exact successful v8 capture through strict, entirely offline presentation."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import openai
import pytest

from app.ai.bindings import _join_segments, canonical_draft, generation_model
from app.ai.client import ResearchClient
from app.ai.prompts import CHAT_TASK, PROMPT_VERSION, SYSTEM_PROMPT
from app.ai.safety import EMAIL_PATTERN, SECRET_PATTERN
from app.ai.schemas import ChatDraft, ResearchAnswer
from app.ai.validation import render_finding, validate_findings
from app.core.config import Settings
from app.main import create_app


FIXTURE = Path(__file__).parent / "fixtures/ai/msft_v8_success.json"
RAW_SHA = "e5ede61fd4602197a661e0adfd9258f3b7acc05108159552a5a0402c262c2a79"


def captured():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def no_real_http(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Real HTTP is prohibited in presentation regressions.")

    async def async_blocked(*args, **kwargs):
        blocked()

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", async_blocked)


def presented(saved=None):
    saved = saved or captured()
    registry = saved["evidence_package"]["registry"]
    typed = generation_model(ChatDraft, {"registry": registry}).model_validate_json(saved["raw_output_text"])
    draft = canonical_draft(ChatDraft, typed, registry)
    validate_findings(draft.answer, registry)
    return [render_finding(finding, registry) for finding in draft.answer]


def test_exact_successful_v8_capture_preserves_words_claims_sources_and_classifications():
    saved = captured()
    before = deepcopy(saved)
    assert hashlib.sha256(saved["raw_output_text"].encode()).hexdigest() == RAW_SHA
    assert not EMAIL_PATTERN.search(saved["raw_output_text"]) and not SECRET_PATTERN.search(saved["raw_output_text"])
    for finding in json.loads(saved["raw_output_text"])["answer"]:
        for part in finding["explanation"]:
            if part["kind"] != "text":
                assert part["evidence_id"] in saved["request_scope"]["evidence_ids"]
                assert part["evidence_id"] in saved["request_scope"]["binding_catalog"][part["kind"]]
                assert part["evidence_id"] in saved["evidence_package"]["registry"]
    results = presented(saved)
    assert results == saved["expected_presented_findings"]
    assert len(results) == 2 and len(saved["evidence_package"]["registry"]) == 7
    for result, original in zip(results, saved["original_published_findings"], strict=True):
        assert re.sub(r"\s", "", result["explanation"]) == re.sub(r"\s", "", original["explanation"])
        for key in ("title", "evidence_ids", "category", "uncertainty", "quantitative_claims"):
            assert result[key] == original[key]
    assert "fair value $619.56 and a dated market comparison price $539.44. Only 1 model contributes: Forward P/E. Many" in results[0]["explanation"]
    assert "details. The estimate" in results[0]["explanation"]
    assert "policies. Hypothetical" in results[1]["explanation"]
    # The captured broad phrase remains original wording; an evidence-owned UI
    # clarification and future prompt instructions distinguish the actual input.
    assert "EBITDA/EBITDA margin" in results[0]["explanation"]
    assert results[0]["quantitative_claims"][0]["value"] == 619.5604742486083
    assert saved == before


@pytest.mark.parametrize(("segments", "expected"), [
    ([("text", "price"), ("value", "{{value:e_id}}"), ("text", "and")], "price {{value:e_id}} and"),
    ([("model", "{{model:e_id}}"), ("text", "."), ("text", "Many methods")], "{{model:e_id}}. Many methods"),
    ([("text", "Observed"), ("date", "{{date:e_id}}"), ("text", ".")], "Observed {{date:e_id}}."),
    ([("text", "Period"), ("period", "{{period:e_id}}"), ("text", "reported")], "Period {{period:e_id}} reported"),
    ([("text", "("), ("value", "{{value:e_id}}"), ("text", ")")], "({{value:e_id}})"),
    ([("value", "{{value:e_id}}"), ("text", ", then "), ("model", "{{model:e_id}}")], "{{value:e_id}}, then {{model:e_id}}"),
    ([("value", "{{value:e_id}}"), ("text", "/"), ("value", "{{value:e_other}}")], "{{value:e_id}}/{{value:e_other}}"),
    ([("text", "un"), ("text", "available")], "unavailable"),
    ([("text", "Already "), ("value", "{{value:e_id}}"), ("text", " spaced.")], "Already {{value:e_id}} spaced."),
    ([("text", "First.\n"), ("text", "Next paragraph")], "First.\nNext paragraph"),
    ([("text", "“"), ("model", "{{model:e_id}}"), ("text", "”")], "“{{model:e_id}}”"),
])
def test_atomic_reference_boundaries_add_only_missing_whitespace(segments, expected):
    assert _join_segments(segments) == expected


def test_prompt_guidance_is_precise_and_keeps_strict_contract():
    assert PROMPT_VERSION == "fairworth-research-10"
    assert "Listing verification is a dated source observation" in SYSTEM_PROMPT
    assert "Neither CIK, listing" in SYSTEM_PROMPT
    assert "EBITDA margin is a" in SYSTEM_PROMPT
    assert "does not\nestablish that EBITDA itself is missing" in SYSTEM_PROMPT
    assert "unless the user asks" in SYSTEM_PROMPT
    assert "at most two concise findings" in CHAT_TASK
    assert "quote's bound observation date rather than its retrieval date" in CHAT_TASK
    assert "Ordinary numerical prose is checked" in SYSTEM_PROMPT


async def replay_capture():
    """Reusable offline replay for tests and local display verification."""
    saved = captured()
    settings = Settings(_env_file=None, ai_research_enabled=True, openai_api_key="fake-test-key",
                        openai_model="gpt-5-mini", ai_client_requests_per_minute=30)
    requests = []

    async def handle(request):
        assert str(request.url) == "https://api.openai.com/v1/responses"
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "resp_offline_v8", "object": "response", "created_at": 0,
            "status": "completed", "model": "gpt-5-mini-2025-08-07", "output": [
                {"id": "msg_offline_v8", "type": "message", "role": "assistant", "status": "completed",
                 "content": [{"type": "output_text", "text": saved["raw_output_text"], "annotations": []}]}]})

    app = create_app(settings)
    async with app.router.lifespan_context(app):
        service = app.state.research_service
        service.assembler = SimpleNamespace(assemble=AsyncMock(return_value=deepcopy(saved["evidence_package"])))
        http = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        sdk = openai.AsyncOpenAI(api_key="fake-test-key", http_client=http, max_retries=0)
        service.client = ResearchClient(settings, sdk)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://fairworth.local") as api:
            headers = {"X-Fairworth-Session": "offline-v8-presentation"}
            response = await api.post("/api/stocks/MSFT/ai/chat", headers=headers,
                                      json={"question": saved["question"], "history": []})
            assert response.status_code == 200
            result = ResearchAnswer.model_validate(response.json()).model_dump(mode="json")
            assert result["answer"] == presented(saved)
            assert len(result["evidence_references"]) == 7
            for source in result["evidence_references"]:
                assert source == saved["evidence_package"]["registry"][source["id"]]
                fetched = await api.get(f'/api/stocks/MSFT/ai/evidence/{source["id"]}', headers=headers,
                                        params={"snapshot_token": result["snapshot_token"]})
                assert fetched.status_code == 200 and fetched.json() == source
    assert len(requests) == 1  # MockTransport only; no real OpenAI call.
    assert requests[0]["store"] is False and requests[0]["tools"] == []
    assert requests[0]["max_output_tokens"] == 5000 and sdk.max_retries == 0
    return result


@pytest.mark.asyncio
async def test_exact_v8_response_replays_through_sdk_fastapi_and_every_source():
    await replay_capture()
