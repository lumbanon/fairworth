"""Actual retained SEC/FMP observations through deterministic engine + mocked AI.

These are not live OpenAI tests. The supported SDK adapter still enforces its real
full input budget and validates a strict structured response from the fake SDK.
"""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from app.ai.client import ResearchClient
from app.ai.context import EvidenceContextAssembler
from app.ai.prompts import SYSTEM_PROMPT
from app.ai.report_service import ResearchService
from app.ai.schemas import (ChatDraft, ChatRequest, Finding, QuantitativeClaim, ReportDraft,
                             ReportRequest, ReportSections)
from app.core.config import Settings
from app.valuation.automatic import prepare_automatic_inputs
from app.valuation.engine import calculate_valuation
from test_automatic_evidence_fixture import examples
from ai_generation_helpers import generation_json


class RealValuationFixtureService:
    def __init__(self, ticker):
        original, evidence = examples()[ticker]
        self.data = prepare_automatic_inputs(original, evidence)

    async def inputs(self, ticker):
        return deepcopy(self.data)

    async def calculate(self, ticker, request):
        return calculate_valuation(deepcopy(self.data), request)


def evidence(package, metric):
    return next(item for item in package["registry"].values() if item["metric"] == metric)


def finding_from(item, title, explanation, category=None):
    quantitative = []
    if isinstance(item["value"], (int, float)) and not isinstance(item["value"], bool):
        quantitative = [QuantitativeClaim(evidence_id=item["id"], metric=item["metric"], value=item["value"],
                          unit=item["unit"], period=item["period"], derivation=item["derivation"])]
    category = category or item["category"]
    return Finding(title=title, explanation=explanation, evidence_ids=[item["id"]], category=category,
                   uncertainty=("unavailable" if category == "unavailable" else "limited" if category in {"policy_estimate", "user_assumption"}
                                else "analytical" if category in {"interpretation", "valuation_output"} else "documented"),
                   quantitative_claims=quantitative)


def grounded_draft(package, schema):
    ticker = package["ticker"]
    revenue = evidence(package, "revenue")
    base = evidence(package, "base_fair_value")
    valuation_text = ("The Python estimate is an illustrative policy-based earnings benchmark with concentrated model evidence."
                      if base["value"] is not None and base["category"] == "policy_estimate" else
                      "The Python estimate reflects explicit user-defined assumptions." if base["value"] is not None else
                      "No defensible weighted intrinsic value is available; missing model inputs remain unavailable.")
    valuation = finding_from(base, f"{ticker} valuation evidence", valuation_text)
    finances = finding_from(revenue, f"{ticker} financial observation", "Reported annual revenue retains its exact fiscal period and currency.")
    models = evidence(package, "base_model_results")
    limitations = finding_from(models, "Evidence limitations", "Missing inputs and dated observations limit interpretation; qualitative filing coverage is unavailable.", "interpretation")
    if schema is ChatDraft:
        answer = [valuation, finances]
        if ticker == "ORCL":
            answer.append(finding_from(evidence(package, "market_price"), "Restricted quote coverage",
                "A permitted market quote is unavailable; the provider restriction is not replaced with an invented comparison price."))
        return ChatDraft(answer=answer)
    profile = evidence(package, "company_profile")
    return ReportDraft(sections=ReportSections(
        executive_summary=[finances, valuation],
        business_overview=[finding_from(profile, f"{ticker} company context", "Company identity and industry context come from the supplied provider records.", "interpretation")],
        financial_analysis=[finances], valuation_analysis=[valuation], risks=[limitations],
        catalysts=[finding_from(models, "Conditional catalysts", "No retrieved filing passage establishes an upcoming company event; changes in model assumptions remain analytical scenarios.", "interpretation")],
        bull_case=[finding_from(evidence(package, "bull_fair_value"), "Optimistic scenario", "This is the existing deterministic optimistic scenario; unavailable outcomes remain unavailable.")],
        bear_case=[finding_from(evidence(package, "bear_fair_value"), "Cautious scenario", "This is the existing deterministic cautious scenario; it does not assign a probability.")],
        valuation_drivers=[finding_from(models, "Valuation drivers", "Model eligibility depends on complete inputs, verified share scope and supported multiple assumptions.", "interpretation")],
        data_limitations=[limitations]))


class MockOpenAIClient(ResearchClient):
    """Exercise official client input/schema logic without sending any requests."""
    def __init__(self, settings):
        self.inputs = []
        self.closed = False
        sdk = SimpleNamespace(responses=SimpleNamespace(create=self.create), close=self.close_sdk)
        super().__init__(settings, sdk=sdk)

    async def close_sdk(self):
        self.closed = True

    async def create(self, **kwargs):
        payload = json.loads(kwargs["input"][0]["content"])["untrusted_data"]
        package = payload.get("evidence", payload)
        schema = ReportDraft if kwargs["text"]["format"]["name"] == "ReportDraft" else ChatDraft
        full_bytes = len((kwargs["instructions"] + kwargs["input"][0]["content"] + json.dumps(kwargs["text"]["format"]["schema"])).encode("utf-8"))
        assert full_bytes <= self.settings.ai_max_context_tokens == 64000
        assert kwargs["instructions"] == SYSTEM_PROMPT
        assert kwargs["store"] is False and kwargs["tools"] == []
        self.inputs.append({"package": deepcopy(package), "full_bytes": full_bytes, "schema": schema})
        draft = grounded_draft(package, schema)
        return SimpleNamespace(status="completed", output_text=generation_json(draft))


def research(ticker, filings=None):
    settings = Settings(_env_file=None, ai_research_enabled=True, openai_api_key="fake-test-key-not-a-credential",
                        openai_model="test-configured-model", fmp_api_key="", sec_user_agent="")
    values = RealValuationFixtureService(ticker)
    assembler = EvidenceContextAssembler(values, None, None, filings,
                                         settings.model_copy(update={"ai_max_context_tokens": 52000}))
    client = MockOpenAIClient(settings)
    return ResearchService(settings, assembler, client), values


@pytest.mark.parametrize("ticker,expected", [("AAPL", 214.2302568301956), ("MSFT", 619.5604742486083), ("NVDA", None), ("ORCL", None)])
@pytest.mark.asyncio
async def test_four_company_reports_and_chat_use_actual_financial_evidence_and_sdk_bounds(ticker, expected):
    service, values = research(ticker)
    original = deepcopy(values.data)
    owner = f"private-test-session-{ticker}"
    report = await service.report(ticker, ReportRequest(), owner)
    assert report["ticker"] == ticker
    assert report["cache_status"] == "miss"
    assert set(report["sections"]) == set(ReportSections.model_fields)
    fair = next(item for item in report["evidence_references"] if item["metric"] == "base_fair_value")
    if expected is None:
        assert fair["value"] is None and fair["category"] == "unavailable"
    else:
        assert fair["value"] == pytest.approx(expected)
        assert fair["category"] == "policy_estimate"
        assert any("policy-based" in warning for warning in report["quality_warnings"])
        assert any("one model" in warning for warning in report["quality_warnings"])
    revenue = next(item for item in report["evidence_references"] if item["metric"] == "revenue")
    source_fact = original["facts"]["revenue"]
    assert revenue["value"] == source_fact["value"] and revenue["unit"] == source_fact["unit"] == "USD"
    assert revenue["source_url"] and revenue["accession"]
    assert source_fact["period"]["end_date"] in revenue["period"]
    assert revenue["retrieved_at"] == source_fact["retrieved_at"]
    assert report["snapshot_dates"]["reporting_period"] == original["reporting_period"]["end_date"]
    cached = await service.report(ticker, ReportRequest(), owner)
    assert cached["cache_status"] == "hit" and len(service.client.inputs) == 1
    answer = await service.chat(ticker, ChatRequest(question=f"Explain {ticker}'s valuation limitations and financial evidence."), owner)
    assert answer["ticker"] == ticker
    assert answer["financial_snapshot_id"] == report["financial_snapshot_id"]
    assert answer["valuation_snapshot_id"] == report["valuation_snapshot_id"]
    assert len(service.client.inputs) == 2
    assert all(item["ticker"] == ticker for item in answer["evidence_references"])
    if ticker == "ORCL":
        quote = next(item for item in answer["evidence_references"] if item["metric"] == "market_price")
        assert quote["value"] is None
        assert any("quote is unavailable" in warning for warning in answer["limitations"])
    returned = service.evidence(ticker, revenue["id"], report["snapshot_token"], owner)
    assert returned == revenue
    assert values.data == original
    assert all(call["full_bytes"] <= 64000 for call in service.client.inputs)
    await service.close()
    assert service.client.closed


@pytest.mark.asyncio
async def test_actual_manual_assumptions_invalidate_report_but_preserve_official_facts():
    service, values = research("AAPL")
    original = deepcopy(values.data)
    default = await service.report("AAPL", ReportRequest(), "private-owner")
    custom = await service.report("AAPL", ReportRequest(valuation={"assumptions": {"forward_eps": 12, "target_pe": 20},
                                  "manual_market_price": {"value": 150.0, "currency": "USD"}, "enabled_models": ["pe"]}), "private-owner")
    assert custom["financial_snapshot_id"] == default["financial_snapshot_id"]
    assert custom["valuation_snapshot_id"] != default["valuation_snapshot_id"]
    item = next(item for item in custom["evidence_references"] if item["metric"] == "base_fair_value")
    assert item["value"] == 240 and item["category"] == "user_assumption"
    assert len(service.client.inputs) == 2
    again = await service.report("AAPL", ReportRequest(), "private-owner")
    assert again["cache_status"] == "hit" and again["valuation_snapshot_id"] == default["valuation_snapshot_id"]
    assert values.data == original


@pytest.mark.asyncio
async def test_valid_maximum_chat_history_is_bounded_with_actual_company_evidence():
    service, _values = research("MSFT")
    question = "Please explain the supported financial observations. " * 28
    assert len(question) <= 1500
    history = [{"role": "user" if index % 2 else "assistant", "content": "context " * 250} for index in range(8)]
    response = await service.chat("MSFT", ChatRequest(question=question, history=history), "private-owner")
    assert response["ticker"] == "MSFT"
    assert service.client.inputs[0]["full_bytes"] <= 64000


@pytest.mark.asyncio
async def test_changed_filing_coverage_invalidates_report_cache_without_changing_valuation():
    class Filings:
        text = "Retained synthetic filing fixture discussing documented operating dependencies."
        async def sections(self, cik, ticker):
            return {"passages": [{"title": "Synthetic filing fixture", "section": "Risk factors", "excerpt": self.text,
                "source_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl.htm",
                "accession": "0000320193-25-000079", "filing_date": "2025-10-31", "form": "10-K",
                "retrieved_at": "2026-10-15T00:00:00Z"}], "warnings": []}
    filings = Filings()
    service, _values = research("AAPL", filings)
    first = await service.report("AAPL", ReportRequest(), "private-owner")
    filings.text = "Changed retained synthetic filing fixture discussing different operating dependencies."
    second = await service.report("AAPL", ReportRequest(), "private-owner")
    assert second["financial_snapshot_id"] == first["financial_snapshot_id"]
    assert second["valuation_snapshot_id"] == first["valuation_snapshot_id"]
    assert second["cache_status"] == "miss"
    assert len(service.client.inputs) == 2
