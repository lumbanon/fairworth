"""Synthetic archived files test exact MSFT attachment; no registry refresh."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.exceptions import ApiError
from app.models import FinancialImportBatch
from app.models.security_registry import SecurityListing
from app.repositories.financial_repository import FinancialRepository, content_hash
from app.services.financial_import_service import apply_preview, build_preview
from phase66_coverage_helpers import import_captured_listings
from test_phase68_financial_import import CLOCK, confirm, counts, retained_source


def archive_spec(tmp_path, identity):
    directory = tmp_path / "archive"
    directory.mkdir()
    listing = directory / "listing.raw"
    listing.write_bytes(b"Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares\n"
        b"MSFT|Microsoft Corporation - Common Stock|Q|N|N|100|N|N\nFile Creation Time: 1021202607:00\n")
    reference = directory / "reference.raw"
    reference.write_text(json.dumps({"fields": ["cik", "name", "ticker", "exchange"],
        "data": [[789019, "Microsoft Corporation", "MSFT", "Nasdaq"]]}))
    manifest = directory / "manifest.json"
    requests = []
    for kind, path, provider, url in (
        ("nasdaqlisted", listing, "nasdaq", "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"),
        ("company_tickers_exchange", reference, "sec", "https://www.sec.gov/files/company_tickers_exchange.json")):
        content = path.read_bytes()
        requests.append({"provider": provider, "endpoint": kind, "url": url, "file": path.name,
            "status": "received", "http_status": 200, "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(), "retrieved_at": "2026-10-21T07:50:00Z"})
    manifest.write_text(json.dumps({"schema_version": "phase671-acquisition-1",
        "authorization_question_id": "call_5bac25295829451a94f814a3c0674f98", "requests": requests}))
    path = tmp_path / "archived-spec.json"
    path.write_text(json.dumps({"version": "phase68-archived-security-package-1", "ticker": "MSFT",
        "instrument_id": identity["instrument_id"], "listing_id": identity["listing_id"],
        "acquisition_manifest": str(manifest), "authorization_question_id": "call_5bac25295829451a94f814a3c0674f98",
        "sources": {"nasdaqlisted": str(listing), "company_tickers_exchange": str(reference)}}))
    return path


@pytest.fixture
def archived_case(session_factory, tmp_path, raw_facts):
    _, registry, _ = import_captured_listings(session_factory)
    identity = registry.resolve("MSFT")
    raw = deepcopy(raw_facts)
    raw["cik"] = 789019
    source = retained_source(tmp_path, raw, "MSFT")
    with session_factory.begin() as session:
        listing = session.get(SecurityListing, identity["listing_id"])
        old = deepcopy(listing.verification)
        old["observed_on"] = "2026-10-19"
        old["issuer_linkage"]["observed_on"] = "2026-10-19"
        old["issuer_linkage"]["retrieved_at"] = None
        listing.verification = old
    return identity, source, archive_spec(tmp_path, identity)


def plan(engine, source, spec):
    return build_preview(engine, [source], as_of=CLOCK, sec_cache_ttl_seconds=21600,
                         archived_security_package=spec)


def test_archived_attachment_preserves_installed_registry_and_uses_exact_new_source_clocks(engine, session_factory, archived_case):
    identity, source, spec = archived_case
    with session_factory() as session:
        old_registry = content_hash(session.get(SecurityListing, identity["listing_id"]).verification)
    frozen = plan(engine, source, spec)
    package = frozen["archived_security"]["package"]
    assert package["issuer_linkage"]["cik"] == "0000789019"
    assert package["identity"]["listing_id"] == identity["listing_id"]
    assert package["proof_expiry"]["listing"]["expires_at"] == "2026-10-22T00:00:00+00:00"
    assert package["issuer_linkage"]["retrieved_at"] == "2026-10-21T07:50:00+00:00"
    assert package["listing_verification"]["original_record"]["Symbol"] == "MSFT"
    assert package["issuer_linkage"]["original_record"]["cik"] == 789019
    result = apply_preview(engine, frozen, confirmation=confirm(frozen))
    imported = FinancialRepository(session_factory).imported_dataset(identity["issuer_id"], identity["cik"])
    assert imported["archived_security_proofs"][identity["listing_id"]] == package
    with session_factory() as session:
        assert content_hash(session.get(SecurityListing, identity["listing_id"]).verification) == old_registry
    assert apply_preview(engine, frozen, confirmation=confirm(frozen))["already_applied"]
    assert result["row_changes"]["financial_facts"] == 24


@pytest.mark.parametrize("mutation", ["wrong_cik", "wrong_venue", "wrong_symbol", "tampered_bytes", "wrong_listing"])
def test_archived_sources_and_selected_security_fail_closed(engine, session_factory, archived_case, mutation):
    identity, source, spec_path = archived_case
    spec = json.loads(spec_path.read_text())
    if mutation == "wrong_listing":
        spec["listing_id"] = "unknown-listing"
        spec_path.write_text(json.dumps(spec))
    else:
        reference = Path(spec["sources"]["company_tickers_exchange"])
        payload = json.loads(reference.read_text())
        if mutation == "wrong_cik": payload["data"][0][0] = 320193
        elif mutation == "wrong_venue": payload["data"][0][3] = "NYSE"
        elif mutation == "wrong_symbol": payload["data"][0][2] = "AAPL"
        if mutation == "tampered_bytes":
            reference.write_bytes(reference.read_bytes() + b" ")
        else:
            reference.write_text(json.dumps(payload))
            manifest = Path(spec["acquisition_manifest"])
            receipt = json.loads(manifest.read_text())
            row = receipt["requests"][1]
            row.update(bytes=reference.stat().st_size, sha256=hashlib.sha256(reference.read_bytes()).hexdigest())
            manifest.write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        plan(engine, source, spec_path)
    assert counts(session_factory)["financial_facts"] == 0


def test_changed_archived_source_after_preview_or_after_apply_is_rejected(engine, session_factory, archived_case):
    _, source, spec_path = archived_case
    frozen = plan(engine, source, spec_path)
    before = counts(session_factory)
    spec = json.loads(spec_path.read_text())
    original = Path(spec["sources"]["nasdaqlisted"])
    data = original.read_bytes()
    original.write_bytes(data + b" ")
    with pytest.raises(ValueError):
        apply_preview(engine, frozen, confirmation=confirm(frozen))
    assert counts(session_factory) == before
    original.write_bytes(data)
    apply_preview(engine, frozen, confirmation=confirm(frozen))
    original.write_bytes(data + b" ")
    with pytest.raises(ValueError):
        apply_preview(engine, frozen, confirmation=confirm(frozen))


def test_archived_attachment_hash_or_owner_cannot_be_reassigned(engine, session_factory, archived_case):
    identity, source, spec = archived_case
    frozen = plan(engine, source, spec)
    result = apply_preview(engine, frozen, confirmation=confirm(frozen))
    with session_factory.begin() as session:
        batch = session.get(FinancialImportBatch, result["batch_id"])
        summary = deepcopy(batch.summary)
        summary["archived_security_proofs"][identity["listing_id"]]["identity"]["cik"] = "0000320193"
        batch.summary = summary
    with pytest.raises(ApiError, match="attachment failed"):
        FinancialRepository(session_factory).imported_dataset(identity["issuer_id"], identity["cik"])


def test_other_issuer_in_same_batch_does_not_receive_or_fail_on_msft_archive(engine, session_factory, archived_case, tmp_path, raw_facts):
    identity, source, spec = archived_case
    raw = deepcopy(raw_facts)
    raw["cik"] = 320193
    other_source = retained_source(tmp_path, raw, "AAPL")
    frozen = build_preview(engine, [source, other_source], as_of=CLOCK, sec_cache_ttl_seconds=21600,
                           archived_security_package=spec)
    apply_preview(engine, frozen, confirmation=confirm(frozen))
    repository = FinancialRepository(session_factory)
    other_identity = frozen["sources"][1]["identity"]
    assert repository.imported_dataset(other_identity["issuer_id"], "0000320193")["archived_security_proofs"] == {}
    assert identity["listing_id"] in repository.imported_dataset(identity["issuer_id"], identity["cik"])["archived_security_proofs"]
