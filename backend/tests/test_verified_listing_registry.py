"""Synthetic exchange/parser regressions, never real market coverage claims."""
from copy import deepcopy
from datetime import UTC, datetime
import hashlib

import pytest
from sqlalchemy import func, select

from app.models import SecurityAlias, SecurityListingObservation, SecurityRegistryRefresh
from app.registry.importers import sec_reference_records
from app.registry.listing_sources import parse_nasdaq_directory, security_form
from app.registry.repository import SecurityRegistryRepository
from app.registry.service import SecurityRegistryService
from types import SimpleNamespace
from test_api import client

RETRIEVED = "2026-10-19T01:00:00+00:00"
SEC = {"source": "sec-edgar-reference", "as_of": "2026-10-18", "source_kind": "reference"}


def directory(*rows, kind="nasdaqlisted", footer="1018202621:31"):
    header = ("Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares"
              if kind == "nasdaqlisted" else
              "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol")
    return (header + "\n" + "\n".join(rows) + "\nFile Creation Time: " + footer + "|||||||\n").encode()


def bundle(*rows, kind="nasdaqlisted", footer="1018202621:31"):
    return parse_nasdaq_directory(directory(*rows, kind=kind, footer=footer), kind, retrieved_at=RETRIEVED)


def sec(repository, rows=None):
    rows = rows or [[1, "Synthetic Alpha", "ZZQA", "Nasdaq"]]
    repository.import_snapshot(sec_reference_records({"fields": ["cik", "name", "ticker", "exchange"], "data": rows}), SEC)


def publish(repository, payload):
    return repository.import_snapshot(payload["records"], payload["provenance"])


def test_directory_preserves_footer_clock_raw_row_hash_and_financial_notice():
    content = directory("ZZQA|Synthetic Alpha - Common Stock|Q|N|D|100|N|N", "ZZQT|Test issue - Common Stock|Q|Y|N|100|N|N")
    payload = parse_nasdaq_directory(content, "nasdaqlisted", retrieved_at=RETRIEVED)
    meta, row = payload["provenance"], payload["records"][0]
    assert meta["as_of"] == "2026-10-18" and meta["published_at"] == "1018202621:31"
    assert meta["source_timezone"] is None and meta["content_hash"] == hashlib.sha256(content).hexdigest()
    assert meta["retrieved_at"] == RETRIEVED and meta["quality"]["excluded_test_issues"] == 1
    assert row["listing_status"] == "active" and row["identity_status"] == "reference_only"
    assert any("not a trading suspension" in item for item in row["warnings"])
    assert row["original_record"]["Financial Status"] == "D"
    assert len(row["source_record_hash"]) == 64 and row["source_security_identifier"] is None
    assert "valid_from" not in row and "cik" not in row


@pytest.mark.parametrize("description,flag,expected", [
    ("Synthetic common stock", "N", "common_stock"), ("Synthetic Class B ordinary shares", "N", "common_stock"),
    ("Synthetic American Depositary Shares", "N", "adr"), ("Synthetic ADS", "N", "adr"),
    ("Synthetic Depositary Shares representing Preferred Stock", "N", "preferred"),
    ("Synthetic Warrants", "N", "warrant"), ("Synthetic Rights", "N", "right"),
    ("Synthetic Units", "N", "unit"), ("Synthetic Closed-end Fund", "N", "closed_end_fund"),
    ("Synthetic Fund", "Y", "etf"), ("Synthetic Unspecified", "N", "unknown"),
    ("Synthetic Bank", "N", "unknown"), ("Synthetic REIT", "N", "unknown"),
    ("Synthetic - Units, each consisting of one common share and one warrant", "N", "unit"),
    ("Synthetic - Units, each consisting of preferred stock and warrants", "N", "unit"),
    ("Synthetic - American Depositary Shares, each representing two ordinary shares", "N", "adr"),
    ("Synthetic Rights Company - Common Stock", "N", "common_stock"),
    ("Synthetic - Rights, each to receive one Common Share", "N", "right"),
    ("Synthetic - Rights to acquire Common Stock", "N", "right"),
])
def test_description_classification_never_uses_symbol_or_company_business(description, flag, expected):
    assert security_form(description, flag) == expected


@pytest.mark.parametrize("code,venue,mic", [("N", "NYSE", "XNYS"), ("A", "NYSE American", "XASE"),
    ("P", "NYSE Arca", "ARCX"), ("Z", "Cboe BZX", "BATS"), ("V", "IEX", "IEXG"), ("?", "?", None)])
def test_official_exchange_codes_and_explicit_symbol_aliases(code, venue, mic):
    row = bundle(f"ZZQ.B|Synthetic Class B Common Stock|{code}|ZZQ.B|N|100|N|ZZQ-B", kind="otherlisted")["records"][0]
    assert row["exchange"] == venue and row["exchange_mic"] == mic
    assert row["symbol_aliases"] == ["ZZQ-B"] and row["share_class"] == "B"
    assert row["listing_status"] == ("active" if mic else "unknown")


def test_preferred_act_syntax_uses_only_an_explicit_source_routing_alias():
    row = bundle("ZZQ$B|Synthetic Depositary Shares Preferred Stock|N|ZZQpB|N|100|N|ZZQ-B", kind="otherlisted")["records"][0]
    assert row["ticker"] == "ZZQ-B" and row["display_symbol"] == "ZZQ$B"
    assert row["security_form"] == "preferred" and row["symbol_aliases"] == []
    assert row["original_record"]["CQS Symbol"] == "ZZQpB"


@pytest.mark.parametrize("mutate", [
    lambda text: text.replace("ETF", "Surprise Flag"),
    lambda text: text.replace("|N|100|N|N", "|N|100|Z|N"),
    lambda text: text.replace("File Creation Time: ", "Missing Footer: "),
    lambda text: text.replace("1018202621:31", "9999202621:31"),
    lambda text: text.replace("|Q|N|N|100|N|N", "|Q|N|N|100|N|N|extra"),
])
def test_directory_schema_flags_and_incomplete_snapshots_fail_closed(mutate):
    text = directory("ZZQA|Synthetic Common Stock|Q|N|N|100|N|N").decode()
    with pytest.raises(ValueError):
        parse_nasdaq_directory(mutate(text).encode(), "nasdaqlisted", retrieved_at=RETRIEVED)


def test_duplicate_security_rows_and_unaware_retrieval_fail_closed():
    content = directory(*(["ZZQA|Synthetic Common Stock|Q|N|N|100|N|N"] * 2))
    with pytest.raises(ValueError, match="duplicate"):
        parse_nasdaq_directory(content, "nasdaqlisted", retrieved_at=RETRIEVED)
    with pytest.raises(ValueError, match="timezone-aware"):
        parse_nasdaq_directory(content, "nasdaqlisted", retrieved_at="2026-10-19T01:00:00")


def test_authoritative_listing_upgrades_unique_sec_reference_without_new_ids(session_factory):
    repository = SecurityRegistryRepository(session_factory)
    sec(repository)
    before = repository.resolve("ZZQA")
    payload = bundle("ZZQA|Synthetic Alpha - Common Stock|Q|N|N|100|N|N")
    result = publish(repository, payload)
    after = repository.resolve("ZZQA")
    assert all(before[field] == after[field] for field in ("issuer_id", "instrument_id", "listing_id", "ticker", "name", "cik"))
    assert after["security_form"] == "common_stock" and after["issuer_business_category"] == "unknown"
    assert after["identity_status"] == "verified" and after["listing_status"] == "active"
    assert after["listing_verification"]["status"] == "verified"
    assert after["listing_verification"]["confidence"] == "source_backed"
    assert after["listing_verification"]["published_at"] == "1018202621:31"
    assert len(after["source_refs"]) == 2
    assert publish(repository, payload)["changed"] is False
    assert repository.retention_plan("2026-10-20")["deletion_performed"] is False
    assert any(item["protected"] for item in repository.retention_plan("2026-10-20")["candidates"])
    history = repository.listing_history(after["listing_id"])
    assert len(history) == 2 and any(item["record"]["original_record"] for item in history)
    assert result["omitted_record_count"] == 0


def test_source_only_listing_does_not_invent_issuer_or_financial_owner(session_factory):
    repository = SecurityRegistryRepository(session_factory)
    publish(repository, bundle("ZZQA|Synthetic Alpha - Common Stock|Q|N|N|100|N|N"))
    identity = repository.resolve("ZZQA")
    assert identity["listing_verification"]["status"] == "verified"
    assert identity["identity_status"] == "reference_only" and identity["cik"] is None


def test_explicit_alias_and_venue_linkage_preserves_canonical_security(session_factory):
    repository = SecurityRegistryRepository(session_factory)
    sec(repository, [[1, "Synthetic Class B", "ZZQ-B", "NYSE"], [1, "Synthetic Class A", "ZZQ-A", "NYSE"]])
    original = repository.resolve("ZZQ-B")
    publish(repository, bundle("ZZQ.B|Synthetic Class B Common Stock|N|ZZQ.B|N|100|N|ZZQ-B", kind="otherlisted"))
    linked = repository.resolve("ZZQ.B")
    assert linked["instrument_id"] == original["instrument_id"] and linked["ticker"] == "ZZQ-B"
    assert linked["display_symbol"] == "ZZQ.B"
    assert repository.resolve("ZZQ-A")["instrument_id"] != linked["instrument_id"]
    assert repository.resolve("ZZQ-A")["listing_status"] == "unknown"


def test_cik_or_name_alone_cannot_merge_instruments_and_wrong_venue_not_linked(session_factory):
    repository = SecurityRegistryRepository(session_factory)
    sec(repository)
    prior = repository.resolve("ZZQA")
    publish(repository, bundle("ZZQB|Synthetic Alpha - Common Stock|Q|N|N|100|N|N"))
    assert repository.resolve("ZZQB")["issuer_id"] != prior["issuer_id"]
    assert repository.resolve("ZZQB")["cik"] is None
    publish(repository, bundle("ZZQA|Synthetic Alpha - Common Stock|N|ZZQA|N|100|N|ZZQA", kind="otherlisted"))
    candidates = repository.search("ZZQA")["results"]
    assert len(candidates) == 2 and len({item["instrument_id"] for item in candidates}) == 2


def test_reference_refresh_cannot_erase_authoritative_classification_or_status(session_factory):
    repository = SecurityRegistryRepository(session_factory)
    sec(repository)
    publish(repository, bundle("ZZQA|Synthetic Alpha - Common Stock|Q|N|N|100|N|N"))
    rows = sec_reference_records({"fields": ["cik", "name", "ticker", "exchange"], "data": [[1, "Synthetic Alpha", "ZZQA", "Nasdaq"]]})
    repository.import_snapshot(rows, {**SEC, "as_of": "2026-10-19"})
    identity = repository.resolve("ZZQA")
    assert identity["listing_status"] == "active" and identity["security_form"] == "common_stock"
    assert identity["registry_as_of"] == "2026-10-18"  # proof date, not import date


def test_explicit_conflicting_authorities_preserved_without_convenient_promotion(session_factory):
    repository = SecurityRegistryRepository(session_factory)
    sec(repository)
    payload = bundle("ZZQA|Synthetic Alpha - Common Stock|Q|N|N|100|N|N")
    publish(repository, payload)
    contradiction = deepcopy(payload)
    contradiction["provenance"]["source"] = "synthetic-independent-listing-authority"
    contradiction["provenance"]["as_of"] = "2026-10-19"
    contradiction["records"][0]["listing_status"] = "suspended"
    contradiction["records"][0]["original_record"] = {"synthetic_status": "suspended"}
    contradiction["records"][0]["source_record_hash"] = None
    publish(repository, contradiction)
    identity = repository.resolve("ZZQA")
    assert identity["listing_status"] == "unknown" and identity["identity_status"] == "conflicting"
    assert identity["listing_verification"]["status"] == "conflicting"
    assert identity["listing_verification"]["conflicts"][0]["field"] == "listing_status"
    assert len(repository.listing_history(identity["listing_id"])) == 3


def test_missing_record_reconciliation_retains_listing_and_reports_omission(session_factory):
    repository = SecurityRegistryRepository(session_factory)
    original = bundle("ZZQA|Synthetic Alpha - Common Stock|Q|N|N|100|N|N", "ZZQB|Synthetic Beta - Common Stock|Q|N|N|100|N|N")
    publish(repository, original)
    result = publish(repository, bundle("ZZQA|Synthetic Alpha - Common Stock|Q|N|N|100|N|N", footer="1019202601:00"))
    assert result["omitted_record_count"] == 1 and result["omitted_source_keys"] == ["ZZQB|NASDAQ"]
    assert repository.resolve("ZZQB")["listing_status"] == "active"
    assert repository.resolve("ZZQB")["registry_as_of"] == "2026-10-18"


def test_source_identity_reassignment_rejected_and_import_rolled_back(session_factory):
    repository = SecurityRegistryRepository(session_factory)
    sec(repository)
    payload = bundle("ZZQA|Synthetic Alpha - Common Stock|Q|N|N|100|N|N")
    publish(repository, payload)
    before = repository.resolve("ZZQA")
    corrupt = deepcopy(payload)
    corrupt["provenance"]["as_of"] = "2026-10-19"
    corrupt["records"][0]["cik"] = "0000000002"
    with pytest.raises(ValueError, match="reassigned"):
        publish(repository, corrupt)
    assert repository.resolve("ZZQA")["issuer_id"] == before["issuer_id"]
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(SecurityRegistryRefresh)) == 2
        assert session.scalar(select(func.count()).select_from(SecurityListingObservation)) == 2


def test_multiple_classes_of_one_issuer_keep_distinct_ids_after_listing_upgrade(session_factory):
    repository = SecurityRegistryRepository(session_factory)
    sec(repository, [[1, "Synthetic Dual Class", "ZZQA", "Nasdaq"], [1, "Synthetic Dual Class", "ZZQB", "Nasdaq"]])
    before = [repository.resolve(symbol) for symbol in ("ZZQA", "ZZQB")]
    publish(repository, bundle("ZZQA|Synthetic Class A Common Stock|Q|N|N|100|N|N", "ZZQB|Synthetic Class B Common Stock|Q|N|N|100|N|N"))
    after = [repository.resolve(symbol) for symbol in ("ZZQA", "ZZQB")]
    assert after[0]["issuer_id"] == after[1]["issuer_id"]
    assert after[0]["instrument_id"] != after[1]["instrument_id"]
    assert [item["instrument_id"] for item in before] == [item["instrument_id"] for item in after]
    assert [item["share_class"] for item in after] == ["A", "B"]


def test_reused_symbol_cannot_reuse_prior_authority_mapping_after_new_sec_issuer(session_factory):
    repository = SecurityRegistryRepository(session_factory)
    sec(repository)
    payload = bundle("ZZQA|Synthetic Alpha - Common Stock|Q|N|N|100|N|N")
    publish(repository, payload)
    new_issuer = sec_reference_records({"fields": ["cik", "name", "ticker", "exchange"],
                                       "data": [[2, "Synthetic New Issuer", "ZZQA", "Nasdaq"]]})
    repository.import_snapshot(new_issuer, {**SEC, "as_of": "2026-10-19"})
    with pytest.raises(ValueError, match="Ambiguous cross-source"):
        publish(repository, bundle("ZZQA|Synthetic New Issuer - Common Stock|Q|N|N|100|N|N", footer="1019202601:00"))


def test_historical_authority_observation_cannot_erase_latest_status(session_factory):
    repository = SecurityRegistryRepository(session_factory)
    sec(repository)
    publish(repository, bundle("ZZQA|Synthetic Alpha - Common Stock|Q|N|N|100|N|N", footer="1019202601:00"))
    older = bundle("ZZQA|Synthetic Alpha - Common Stock|Q|N|N|100|N|N", footer="1018202621:31")
    older["records"][0]["listing_status"] = "suspended"
    publish(repository, older)
    identity = repository.resolve("ZZQA")
    assert identity["listing_status"] == "active" and identity["registry_as_of"] == "2026-10-19"
    assert len(repository.listing_history(identity["listing_id"])) == 3


def test_bank_common_stock_form_remains_separate_from_business_category(session_factory):
    repository = SecurityRegistryRepository(session_factory)
    row = sec_reference_records({"fields": ["cik", "name", "ticker", "exchange"],
                                  "data": [[1, "Synthetic Bank", "ZZQA", "Nasdaq"]]})[0]
    row.update(issuer_business_category="bank", issuer_classification_evidence={"source": "synthetic verified issuer SIC"})
    repository.import_snapshot([row], SEC)
    publish(repository, bundle("ZZQA|Synthetic Bank - Common Stock|Q|N|N|100|N|N"))
    identity = repository.resolve("ZZQA")
    assert identity["security_form"] == "common_stock" and identity["issuer_business_category"] == "bank"
    assert identity["issuer_classification_evidence"]["source"] == "synthetic verified issuer SIC"


def test_mass_missing_snapshot_quarantined_atomically_instead_of_delisting(session_factory):
    repository = SecurityRegistryRepository(session_factory)
    rows = [f"ZZ{index:04d}|Synthetic {index} - Common Stock|Q|N|N|100|N|N" for index in range(100)]
    publish(repository, bundle(*rows))
    with pytest.raises(ValueError, match="quality quarantine"):
        publish(repository, bundle(*rows[:30], footer="1019202601:00"))
    assert repository.resolve("ZZ0099")["listing_status"] == "active"
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(SecurityRegistryRefresh)) == 1


@pytest.mark.asyncio
async def test_new_sec_refresh_does_not_hide_older_authoritative_listing_date(session_factory, monkeypatch):
    monkeypatch.setattr("app.registry.service.utcnow", lambda: datetime(2026, 10, 25, 12, tzinfo=UTC))
    repository = SecurityRegistryRepository(session_factory)
    sec(repository)
    publish(repository, bundle("ZZQA|Synthetic Alpha - Common Stock|Q|N|N|100|N|N"))
    rows = sec_reference_records({"fields": ["cik", "name", "ticker", "exchange"],
                                  "data": [[1, "Synthetic Alpha", "ZZQA", "Nasdaq"]]})
    repository.import_snapshot(rows, {**SEC, "as_of": "2026-10-25"})
    service = SecurityRegistryService(session_factory, SimpleNamespace(registry_cache_ttl_seconds=86400))
    identity = await service.resolve("ZZQA")
    assert identity["registry_status"] == "stale"
    assert identity["listing_verification"]["status"] == "verified"  # historical proof remains inspectable
    assert identity["listing_verification"]["stale"] is True
    assert identity["listing_verification"]["observed_on"] == "2026-10-18"


def test_enrichment_preserves_alias_provenance_and_prior_company_name_discovery(session_factory):
    repository = SecurityRegistryRepository(session_factory)
    rows = sec_reference_records({"fields": ["cik", "name", "ticker", "exchange"],
                                  "data": [[1, "Original Synthetic Company", "ZZQA", "Nasdaq"]]})
    rows[0].update(aliases=["Old Business Name"], symbol_aliases=["ZZQ-A"])
    repository.import_snapshot(rows, SEC)
    publish(repository, bundle("ZZQA|Current Display Description - Common Stock|Q|N|N|100|N|N"))
    assert repository.search("original synthetic")["results"][0]["ticker"] == "ZZQA"
    assert repository.search("old business")["results"][0]["ticker"] == "ZZQA"
    with session_factory() as session:
        previous = session.scalar(select(SecurityAlias).where(SecurityAlias.normalized_value == "ZZQ-A"))
        assert {item["provider"] for item in previous.source_refs} == {"sec-edgar"}
        canonical = session.scalar(select(SecurityAlias).where(SecurityAlias.normalized_value == "ZZQA"))
        assert {item["provider"] for item in canonical.source_refs} == {"sec-edgar", "nasdaq-trader"}


@pytest.mark.parametrize("budget", ["snapshots", "observations"])
def test_history_budget_is_atomic_and_idempotent_reimport_allowed_at_limit(session_factory, budget):
    repository = SecurityRegistryRepository(session_factory, max_source_snapshots=1 if budget == "snapshots" else 128,
                                           max_observations=1 if budget == "observations" else 2_000_000)
    payload = bundle("ZZQA|Synthetic Alpha - Common Stock|Q|N|N|100|N|N")
    first = publish(repository, payload)
    assert publish(repository, payload)["refresh_id"] == first["refresh_id"]
    assert publish(repository, payload)["changed"] is False
    with pytest.raises(ValueError, match="history budget"):
        publish(repository, bundle("ZZQA|Synthetic Alpha - Common Stock|Q|N|N|100|N|N", footer="1019202601:00"))
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(SecurityRegistryRefresh)) == 1
        assert session.scalar(select(func.count()).select_from(SecurityListingObservation)) == 1


@pytest.mark.parametrize("limits", [{"max_source_snapshots": 0}, {"max_source_snapshots": 10001},
                                   {"max_observations": 0}, {"max_observations": 10000001}])
def test_administrative_history_limits_are_bounded(session_factory, limits):
    with pytest.raises(ValueError, match="budgets"):
        SecurityRegistryRepository(session_factory, **limits)


def test_api_listing_status_filter_is_bounded_paginated_and_validated(client):
    from test_security_registry import PROVENANCE, record
    factory = client.app.state.session_factory
    repository = SecurityRegistryRepository(factory)
    repository.import_snapshot([record("ZZQA"), record("ZZQB"), record("ZZQC"),
        record("ZZQD", listing_status="suspended"), record("ZZQE", listing_status="unknown")], PROVENANCE)
    client.app.state.company_service.registry = SecurityRegistryService(factory, client.app.state.settings)
    first = client.get("/api/stocks/search", params={"q": "ZZQ", "listing_status": "active", "limit": 2})
    assert first.status_code == 200
    body = first.json()
    assert [row["ticker"] for row in body["results"]] == ["ZZQA", "ZZQB"]
    assert body["has_more"] and body["next_offset"] == 2
    second = client.get("/api/stocks/search", params={"q": "ZZQ", "listing_status": "active", "limit": 2, "offset": 2}).json()
    assert [row["ticker"] for row in second["results"]] == ["ZZQC"]
    assert second["has_more"] is False and second["next_offset"] is None
    suspended = client.get("/api/stocks/search", params={"q": "ZZQ", "listing_status": "suspended"}).json()
    assert [row["ticker"] for row in suspended["results"]] == ["ZZQD"]
    unknown = client.get("/api/stocks/search", params={"q": "ZZQ", "listing_status": "unknown"}).json()
    assert [row["ticker"] for row in unknown["results"]] == ["ZZQE"]
    assert client.get("/api/stocks/search?q=ZZQ&listing_status=imaginary").status_code == 422


def test_legacy_search_cannot_pretend_to_filter_unverified_provider_references(client, fake_providers):
    before = fake_providers[0].company_calls
    body = client.get("/api/stocks/search?q=MSFT&listing_status=active").json()
    assert body["results"] == [] and body["status"] == "partial"
    assert body["warnings"][0]["code"] == "listing_filter_unavailable"
    assert fake_providers[0].company_calls == before


@pytest.mark.parametrize("url", ["https://example.invalid/reference?secret=fixture-private",
    "https://example.invalid/reference?unexpected=fixture-private", "https://example.invalid/reference#fixture-private",
    "https://user:fixture-private@example.invalid/reference", "https://example.invalid:8443/reference", "http://example.invalid/reference"])
def test_source_urls_cannot_export_sensitive_or_unaudited_url_material(session_factory, url):
    repository = SecurityRegistryRepository(session_factory)
    payload = bundle("ZZQA|Synthetic Alpha - Common Stock|Q|N|N|100|N|N")
    payload["provenance"]["source_url"] = url
    with pytest.raises(ValueError, match="URLs|credentials"):
        publish(repository, payload)
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(SecurityRegistryRefresh)) == 0


def test_name_only_alias_provenance_is_not_promoted_to_security_symbol_proof(session_factory):
    repository = SecurityRegistryRepository(session_factory)
    rows = sec_reference_records({"fields": ["cik", "name", "ticker", "exchange"],
                                  "data": [[1, "Synthetic Company", "ZZQA", "NYSE"]]})
    rows[0]["aliases"] = ["ZZQ-A"]  # Company-name search alias, not a security symbol.
    repository.import_snapshot(rows, SEC)
    publish(repository, bundle("ZZQA|Synthetic Company Common Stock|N|ZZQA|N|100|N|ZZQ-A", kind="otherlisted"))
    assert repository.resolve("ZZQ-A")["ticker"] == "ZZQA"
    with session_factory() as session:
        alias = session.scalar(select(SecurityAlias).where(SecurityAlias.normalized_value == "ZZQ-A"))
        assert alias.kind == "symbol_alias"
        assert {ref["provider"] for ref in alias.source_refs} == {"nasdaq-trader"}


@pytest.mark.parametrize("replacement", ["Synthetic - Class B Common Stock", "Synthetic - Class A Preferred Stock"])
def test_same_source_mapped_identity_class_or_form_change_requires_reconciliation(session_factory, replacement):
    repository = SecurityRegistryRepository(session_factory)
    original = bundle("ZZQA|Synthetic - Class A Common Stock|Q|N|N|100|N|N")
    publish(repository, original)
    before = repository.resolve("ZZQA")
    with pytest.raises(ValueError, match="lifecycle reconciliation"):
        publish(repository, bundle(f"ZZQA|{replacement}|Q|N|N|100|N|N", footer="1019202601:00"))
    after = repository.resolve("ZZQA")
    assert after["instrument_id"] == before["instrument_id"] and after["share_class"] == "A"
    assert after["security_form"] == "common_stock"
    assert len(repository.listing_history(after["listing_id"])) == 1


def test_same_source_unknown_classification_can_become_verified_without_new_identity(session_factory):
    repository = SecurityRegistryRepository(session_factory)
    publish(repository, bundle("ZZQA|Synthetic unspecified security|Q|N|N|100|N|N"))
    before = repository.resolve("ZZQA")
    publish(repository, bundle("ZZQA|Synthetic - Class A Common Stock|Q|N|N|100|N|N", footer="1019202601:00"))
    after = repository.resolve("ZZQA")
    assert after["instrument_id"] == before["instrument_id"]
    assert after["share_class"] == "A" and after["security_form"] == "common_stock"


def test_other_source_disagreement_keeps_both_observations_instead_of_identity_mutation(session_factory):
    repository = SecurityRegistryRepository(session_factory)
    sec(repository)
    original = bundle("ZZQA|Synthetic - Class A Common Stock|Q|N|N|100|N|N")
    publish(repository, original)
    before = repository.resolve("ZZQA")
    incompatible = bundle("ZZQA|Synthetic - Class B Preferred Stock|Q|N|N|100|N|N", footer="1019202601:00")
    incompatible["provenance"]["source"] = "synthetic-other-authority"
    publish(repository, incompatible)
    after = repository.resolve("ZZQA")
    assert after["instrument_id"] == before["instrument_id"]
    assert after["listing_verification"]["status"] == "conflicting"
    assert {item["field"] for item in after["listing_verification"]["conflicts"]} == {"security_form", "share_class"}
    assert len(repository.listing_history(after["listing_id"])) == 3

