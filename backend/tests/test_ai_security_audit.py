"""Adversarial regression cases for private data, source identity and admission."""

import asyncio
from copy import deepcopy
import json
from urllib.parse import quote

import pytest

from app.ai.limits import UsageLimits
from app.ai.middleware import ResearchBodyLimit
from app.ai.schemas import Finding, ReportRequest, ReportDraft, ReportSections
from app.ai.validation import validate_findings
from app.core.exceptions import ApiError
from test_ai_research_service import configured, finding, package, service


@pytest.mark.asyncio
async def test_report_cache_invalidates_when_qualitative_evidence_changes():
    research = service()
    first = await research.report("AAPL", ReportRequest(), "owner")
    changed = deepcopy(research.assembler.assemble.return_value)
    changed["registry"]["e_filing"] = {
        **changed["registry"]["e_revenue"], "id": "e_filing", "category": "filing_excerpt",
        "title": "Retrieved business overview", "metric": "filing_passage", "value": "Business overview",
        "unit": "text", "excerpt": "A newly retrieved public filing changes the documented source coverage.",
    }
    research.assembler.assemble.return_value = changed
    second = await research.report("AAPL", ReportRequest(), "owner")
    assert first["cache_status"] == second["cache_status"] == "miss"
    assert research.client.generate.await_count == 2


@pytest.mark.asyncio
async def test_report_cache_invalidates_when_source_limitations_change():
    research = service()
    await research.report("AAPL", ReportRequest(), "owner")
    changed = deepcopy(research.assembler.assemble.return_value)
    changed["limitations"].append("The previously available filing source is stale after an access restriction.")
    research.assembler.assemble.return_value = changed
    assert (await research.report("AAPL", ReportRequest(), "owner"))["cache_status"] == "miss"
    assert research.client.generate.await_count == 2


@pytest.mark.parametrize("number", ["９９９", "٩٩٩", "९९९", "Ⅻ", "½", "²"])
def test_unicode_numeric_assertions_cannot_bypass_structured_claim_validation(number):
    candidate = finding()
    candidate.explanation = f"Reported revenue was {number} USD during the fiscal period."
    with pytest.raises(ApiError):
        validate_findings([candidate], package()["registry"])


@pytest.mark.asyncio
async def test_bare_database_password_never_enters_ai_payload():
    password = "private_database_password_for_offline_test"
    research = service(configured(database_url=f"postgresql+psycopg://fixture:{password}@127.0.0.1/fixture"))
    research.assembler.assemble.return_value["company_name"] = f"Fixture public profile {password}"
    result = await research.report("AAPL", ReportRequest(), "owner")
    sent = research.client.generate.call_args.args[1]
    assert password not in json.dumps(sent)
    assert password not in json.dumps(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("password", ["private_database_password_for_offline_test", 'private_database_"quoted_password', "private_database_\\escaped_password"])
async def test_known_private_strings_are_rejected_if_returned_in_model_prose(password):
    research = service(configured(database_url=f"postgresql+psycopg://fixture:{quote(password, safe='')}@127.0.0.1/fixture"))
    candidate = finding()
    candidate.explanation = f"The source annotation is {password}."
    research.client.generate.return_value = ReportDraft(sections=ReportSections(
        **{section: [candidate] for section in ReportSections.model_fields}))
    with pytest.raises(ApiError):
        await research.report("AAPL", ReportRequest(), "owner")
    assert not research.reports and not research.snapshots


def test_rejected_rotating_sessions_cannot_fill_global_client_capacity():
    limits = UsageLimits(configured(ai_client_requests_per_minute=1), clock=lambda: 10.)
    address = "192.0.2.1"
    limits.throttle(limits.identity("original_session_for_test", address), address)
    initial_keys = set(limits.clients)
    for index in range(20):
        with pytest.raises(ApiError):
            limits.throttle(limits.identity(f"rotated_session_for_test_{index}", address), address)
    assert set(limits.clients) == initial_keys
    unrelated = "192.0.2.2"
    limits.throttle(limits.identity("another_session_for_test", unrelated), unrelated)


@pytest.mark.parametrize("category", ["filing_excerpt", "company_profile"])
def test_documented_company_narrative_has_a_valid_source_category(category):
    evidence = package()["registry"]["e_revenue"]
    evidence = {**evidence, "category": category, "metric": "business_description", "value": "Provider or filing narrative"}
    candidate = Finding(title="Documented business description", explanation="The source describes the company's enterprise software operations.",
                        evidence_ids=[evidence["id"]], category=category,
                        uncertainty="documented", quantitative_claims=[])
    assert validate_findings([candidate], {evidence["id"]: evidence}) == [evidence["id"]]


@pytest.mark.parametrize("prose", ["The stock is a Buy.", "We recommend sell.", "You should hold the stock.",
                                   "Profits are guaranteed.", "The scenario promises risk-free profits."])
def test_valid_citation_cannot_legitimize_obvious_recommendations_or_guarantees(prose):
    candidate = finding()
    candidate.explanation = prose
    candidate.category = "interpretation"
    candidate.uncertainty = "analytical"
    with pytest.raises(ApiError):
        validate_findings([candidate], package()["registry"])


@pytest.mark.parametrize("chunks", [[b"x" * 32769], [b"x" * 16384, b"x" * 16385]])
@pytest.mark.asyncio
async def test_oversized_asgi_chunks_are_rejected_before_buffer_copy(monkeypatch, chunks):
    downstream, messages, copies = [], [], []

    class BoundedBuffer(bytearray):
        def extend(self, chunk):
            assert len(self) + len(chunk) <= 32768
            copies.append(len(chunk))
            super().extend(chunk)

    async def app(scope, receive, send):
        downstream.append(True)

    iterator = iter(chunks)

    async def receive():
        return {"type": "http.request", "body": next(iterator), "more_body": True}

    async def send(message):
        messages.append(message)

    monkeypatch.setattr("app.ai.middleware.bytearray", BoundedBuffer, raising=False)
    await ResearchBodyLimit(app)({"type": "http", "path": "/api/stocks/AAPL/ai/report", "method": "POST"}, receive, send)
    assert not downstream
    assert messages[0]["status"] == 413
    assert sum(copies) <= 32768
    assert json.loads(messages[1]["body"])["error"]["code"] == "ai_request_too_large"


@pytest.mark.asyncio
async def test_slow_request_upload_is_cancelled_with_safe_timeout(monkeypatch):
    actual_timeout = asyncio.timeout
    downstream, messages, deadlines, cancelled = [], [], [], []

    def short_timeout(seconds):
        deadlines.append(seconds)
        return actual_timeout(0.01)

    async def app(scope, receive, send):
        downstream.append(True)

    async def receive():
        try:
            await asyncio.sleep(60)
        finally:
            cancelled.append(True)

    async def send(message):
        messages.append(message)

    monkeypatch.setattr("app.ai.middleware.asyncio.timeout", short_timeout)
    await ResearchBodyLimit(app)({"type": "http", "path": "/api/stocks/AAPL/ai/chat", "method": "POST"}, receive, send)
    assert not downstream and cancelled == [True] and deadlines == [10]
    assert messages[0]["status"] == 408
    assert json.loads(messages[1]["body"])["error"]["code"] == "ai_request_timeout"


@pytest.mark.asyncio
async def test_allowed_chunked_request_reaches_downstream_unchanged():
    original = b"x" * 32768
    messages = iter([{"type": "http.request", "body": original[:16000], "more_body": True},
                     {"type": "http.request", "body": original[16000:], "more_body": False}])
    delivered = []

    async def receive():
        return next(messages)

    async def send(message):
        raise AssertionError("Allowed request must not be rejected by the middleware")

    async def app(scope, receive, send):
        delivered.append(await receive())

    await ResearchBodyLimit(app)({"type": "http", "path": "/api/stocks/AAPL/ai/chat", "method": "POST"}, receive, send)
    assert delivered == [{"type": "http.request", "body": original, "more_body": False}]
