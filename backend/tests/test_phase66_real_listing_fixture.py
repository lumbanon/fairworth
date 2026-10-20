"""Actual approved directory rows; financial coverage remains retained and dated."""
import hashlib
import json

import pytest

from app.registry.coverage_audit import financial_matrix
from app.registry.repository import _public_reference
from app.registry.schemas import RegistryRecord
from phase66_coverage_helpers import captured_listings, import_captured_listings, replay_verified_sample


def test_exact_public_source_rows_and_acquisition_clocks_are_reproducible():
    fixture = captured_listings()
    assert len(fixture["samples"]) == 30
    _public_reference(fixture)
    assert {source["content_hash"] for source in fixture["sources"]} == {
        "e53df7b657e8d358300234b78323f3d62db0d30b70e20ebb8f76c8d8bde6f487",
        "5c301c1313e61742bc6c9536eafc214949df76c9276ccb8df12c849115dde94e"}
    for source in fixture["sources"]:
        assert source["as_of"] == "2026-10-19"
        assert source["published_at"] == "1019202607:00" and source["source_timezone"] is None
        assert source["retrieved_at"].startswith("2026-10-19T11:45:39.")
    for sample in fixture["samples"]:
        row = RegistryRecord.model_validate(sample["listing_record"])
        hashed = hashlib.sha256(json.dumps(row.original_record, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        assert hashed == row.source_record_hash


def test_real_classes_and_unproved_punctuation_or_venue_mappings_stay_separate(session_factory):
    fixture, repository, original = import_captured_listings(session_factory)
    assert repository.resolve("GOOG")["instrument_id"] != repository.resolve("GOOGL")["instrument_id"]
    assert repository.resolve("GOOG")["issuer_id"] == repository.resolve("GOOGL")["issuer_id"]
    assert repository.resolve("GOOG")["security_form"] == "unknown"  # Capital Stock alone is not common-stock proof.
    assert repository.resolve("BABA")["security_form"] == "adr"
    assert repository.resolve("AGNCN")["security_form"] == "preferred"
    assert repository.resolve("BRK.B")["cik"] is None
    assert repository.resolve("BRK.B")["instrument_id"] != repository.resolve("BRK-B")["instrument_id"]
    assert repository.resolve("AAPL")["listing_id"] == original["AAPL"]["listing_id"]
    for symbol, expected_mic in (("SPY", "ARCX"), ("CMT", "XASE")):
        matches = [item for item in repository.search(symbol, 50)["results"]
                   if item["exchange_mic"] == expected_mic and item["listing_verification"].get("status") == "verified"]
        assert len(matches) == 1 and matches[0]["cik"] is None


@pytest.mark.asyncio
async def test_thirty_actual_listings_with_retained_financials_replay_without_new_values(session_factory):
    bundle = await replay_verified_sample(session_factory)
    report = financial_matrix(bundle)
    assert report["sample_denominator"] == 30
    assert report["issuer_denominator"] == 26 and report["unresolved_issuer_listing_count"] == 3
    assert report["stage_status_counts"]["active_listing"] == {"available": 30}
    assert report["stage_status_counts"]["security_identity"] == {"available": 27, "missing_evidence": 3}
    assert report["stage_status_counts"]["classification"] == {"available": 28, "missing_evidence": 2}
    assert report["securities_with_statements"] == 5
    assert report["securities_with_contributing_models"] == 2
    assert all(sample["financial_data_mode"] == "retained_public" for sample in bundle["samples"])
    values = {row["requested_symbol"]: row for row in bundle["samples"]}
    assert values["AAPL"]["retained_default_fair_value"] == 214.2302568301956
    assert values["MSFT"]["retained_default_fair_value"] == 619.5604742486083
    assert values["AAPL"]["retained_default_classification"] == values["MSFT"]["retained_default_classification"] == "policy_based"
    assert values["NVDA"]["retained_default_fair_value"] is values["ORCL"]["retained_default_fair_value"] is None
