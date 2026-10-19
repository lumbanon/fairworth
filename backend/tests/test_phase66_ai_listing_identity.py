"""Synthetic listing observations and mocked generation; no external requests."""
from copy import deepcopy

import pytest

from app.ai.evidence import EvidenceRegistry, safe_source_url, security_identity
from app.ai.schemas import ReportRequest, ChatDraft, ChatRequest, ResearchAnswer
from app.ai.bindings import canonical_draft, generation_model
from app.core.exceptions import ApiError
from test_phase65_ai_identity import ScopedValuations, assembler, identity, scoped_package
from test_ai_research_service import service
from test_valuation_engine import synthetic_inputs  # noqa: F401 -- shared fixture


def verified_identity():
    return {**identity(), "security_form": "common_stock", "issuer_business_category": "bank",
            "listing_verification": {"status": "verified", "confidence": "source_backed",
                "source": "synthetic-listing-authority", "observed_on": "2026-10-16",
                "effective_on": None, "published_at": "1016202617:00", "source_timezone": None,
                "retrieved_at": "2026-10-19T00:00:00Z", "record_hash": "a" * 64,
                "issuer_linkage": {"source": "synthetic-sec-reference", "observed_on": "2026-10-16",
                    "registry_version": "c" * 64, "ticker": "SYN", "cik": None, "exchange_mic": "XTST"},
                "source_url": "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"}}


@pytest.mark.asyncio
async def test_dated_listing_proof_survives_assembly_without_inferred_share_basis(synthetic_inputs):
    values = ScopedValuations(synthetic_inputs)
    values.data["company"].update(verified_identity())
    result = await assembler(values).assemble("SYN", instrument_id="class-a")
    records = [item for item in result["registry"].values() if item["metric"] == "listing_verification"]
    assert len(records) == 1
    proof = records[0]
    assert proof["observation_date"] == "2026-10-16"
    assert proof["retrieved_at"] == "2026-10-19T00:00:00Z"
    assert proof["value"]["security_form"] == "common_stock"
    assert proof["value"]["issuer_business_category"] == "bank"
    assert proof["value"]["verification"]["source_timezone"] is None
    assert proof["source_url"].endswith("/nasdaqlisted.txt")
    assert all(item["identity"] == result["identity"] for item in result["registry"].values())
    assert "share_basis_verified" not in proof["value"]


@pytest.mark.parametrize("url", [
    "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt/anything",
    "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt?key=private",
    "https://user:password@www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
    "https://www.nasdaqtrader.com/otherlisted.txt",
    "http://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
])
def test_listing_citation_url_is_exact_public_path_only(url):
    assert safe_source_url(url) is None


def test_both_official_directory_citations_allowed():
    for filename in ("nasdaqlisted.txt", "otherlisted.txt"):
        url = "https://www.nasdaqtrader.com/dynamic/SymDir/" + filename
        assert safe_source_url(url) == url


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("security_form", "preferred"),
    ("issuer_business_category", "insurance"), ("record_hash", "b" * 64),
    ("status", "conflicting"), ("observed_on", "2026-10-15")])
async def test_mixed_listing_observation_rejected_before_mocked_generation(field, value):
    target = service()
    data = scoped_package()
    data["identity"] = security_identity(verified_identity())
    for record in data["registry"].values():
        record["identity"] = deepcopy(data["identity"])
    changed = data["registry"]["e_revenue"]["identity"]
    if field in {"security_form", "issuer_business_category"}:
        changed[field] = value
    else:
        changed["listing_verification"][field] = value
    target.assembler.assemble.return_value = data
    with pytest.raises(ApiError) as error:
        await target.report("SYN", ReportRequest(), "owner", "class-a")
    assert error.value.code == "ai_identity_mismatch"
    target.client.generate.assert_not_awaited()


def test_equal_financial_values_do_not_reuse_changed_listing_evidence_ids():
    company = verified_identity()
    def key():
        return EvidenceRegistry("SYN", company).add(category="reported_fact", provider="synthetic",
            title="Synthetic revenue", metric="revenue", value=100, unit="USD", period="FY2025")
    original = key()
    company["listing_verification"]["record_hash"] = "b" * 64
    assert key() != original
    listing_changed = key()
    company["listing_verification"]["issuer_linkage"]["observed_on"] = "2026-10-15"
    assert key() != listing_changed


@pytest.mark.asyncio
async def test_report_cache_invalidates_listing_proof_with_unchanged_financial_snapshot():
    target = service()
    data = scoped_package()
    def revise():
        data["identity"] = security_identity(company)
        for item in data["registry"].values():
            item["identity"] = deepcopy(data["identity"])
        target.assembler.assemble.return_value = deepcopy(data)
    company = verified_identity()
    revise()
    first = await target.report("SYN", ReportRequest(), "owner", "class-a")
    assert (await target.report("SYN", ReportRequest(), "owner", "class-a"))["cache_status"] == "hit"
    company["listing_verification"]["record_hash"] = "b" * 64
    revise()
    second = await target.report("SYN", ReportRequest(), "owner", "class-a")
    assert target.client.generate.await_count == 2
    assert first["snapshot_token"] != second["snapshot_token"]
    assert second["financial_snapshot_id"] == first["financial_snapshot_id"]
    assert second["identity"]["listing_verification"]["record_hash"] == "b" * 64
    await target.close()


@pytest.mark.asyncio
async def test_mocked_listing_answer_passes_complete_typed_citation_privacy_and_rendering_pipeline(synthetic_inputs):
    values = ScopedValuations(synthetic_inputs)
    values.data["company"].update(verified_identity())
    data = await assembler(values).assemble("SYN", instrument_id="class-a")
    source = next(item for item in data["registry"].values() if item["metric"] == "listing_verification")
    from app.ai.bindings import binding_kinds
    assert binding_kinds(source) == ()  # Structured listing proof stays citation-only.
    raw = {"answer": [{"title": "Listing scope", "category": "interpretation", "uncertainty": "limited",
        "explanation": [{"kind": "text", "text": "The directory provides a dated listing observation. Listing membership does not establish a compatible financial share basis."}],
        "evidence_ids": [source["id"]], "quantitative_claims": []}]}
    typed = generation_model(ChatDraft, data).model_validate(raw)
    canonical = canonical_draft(ChatDraft, typed, data["registry"])
    target = service()
    target.assembler.assemble.return_value = data
    target.client.generate.return_value = canonical
    result = await target.chat("SYN", ChatRequest(question="Is this a verified listing with compatible financial evidence?"), "owner", "class-a")
    published = ResearchAnswer.model_validate(result).model_dump(mode="json")
    assert len(published["answer"]) == 1
    assert "dated listing observation" in published["answer"][0]["explanation"]
    assert published["answer"][0]["evidence_ids"] == [source["id"]]
    assert published["evidence_references"][0]["source_url"] == source["source_url"]
    assert published["identity"] == source["identity"]
    assert target.evidence("SYN", source["id"], result["snapshot_token"], "owner", "class-a")["observation_date"] == "2026-10-16"
    target.client.generate.assert_awaited_once()
    await target.close()
