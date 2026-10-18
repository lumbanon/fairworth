"""Synthetic identity mechanics, never evidence of actual market coverage."""
import asyncio
from pathlib import Path
from datetime import UTC, datetime
import time
from types import SimpleNamespace

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, event, func, inspect, select
from sqlalchemy.pool import StaticPool

from app.core.exceptions import ApiError
from app.models import SecurityAlias, SecurityInstrument, SecurityIssuer, SecurityListing, SecurityRegistryRefresh
from app.registry.importers import sec_reference_records, import_sec_file
from app.registry.repository import SecurityRegistryRepository
from app.registry.service import SecurityRegistryService


PROVENANCE = {"source": "synthetic-offline-tests", "as_of": "2026-10-18", "complete_scope": False,
              "scope": "Synthetic identity regression only; not real listed securities.", "rights": "Generated test records."}


def test_local_sec_import_retains_hash_without_inventing_classification(session_factory, tmp_path):
    import json
    path = tmp_path / "synthetic-reference.json"
    path.write_text(json.dumps({"fields": ["cik", "name", "ticker", "exchange"],
                                "data": [[1, "Synthetic issuer", "ZZQ", "Synthetic Venue"]]}), encoding="utf-8")
    repository = SecurityRegistryRepository(session_factory)
    result = import_sec_file(repository, path, "2026-10-18")
    assert result["record_count"] == 1
    assert repository.resolve("ZZQ")["instrument_type"] == "unknown"
    assert repository.resolve("ZZQ")["listing_status"] == "unknown"
    with session_factory() as session:
        provenance = session.scalar(select(SecurityRegistryRefresh)).provenance
        assert provenance["notes"][0].startswith("Source SHA256 ")


def record(ticker="ZZQA", cik="0000000001", **overrides):
    return {"ticker": ticker, "name": "Synthetic Quantum Analysis Corporation", "cik": cik,
            "exchange": "Synthetic Test Venue", "exchange_mic": "XTST", "listing_status": "active",
            "identity_status": "verified", "instrument_type": "common_stock",
            "classification_evidence": {"source": "Synthetic fixture", "type_verified": True},
            "source_refs": [{"provider": "synthetic-offline-tests", "record": ticker}], **overrides}


def counts(factory):
    with factory() as session:
        return [session.scalar(select(func.count()).select_from(model)) for model in
                (SecurityIssuer, SecurityInstrument, SecurityListing, SecurityAlias, SecurityRegistryRefresh)]


def test_registry_import_idempotent_and_retrieval_time_not_new_identity(session_factory):
    repository = SecurityRegistryRepository(session_factory)
    first = repository.import_snapshot([record()], PROVENANCE)
    original = repository.resolve("zzqa")
    second = repository.import_snapshot([record()], {**PROVENANCE, "retrieved_at": "2026-10-18T15:00:00Z"})
    assert second["changed"] is False
    assert second["refresh_id"] == first["refresh_id"]
    assert repository.resolve("ZZQA")["instrument_id"] == original["instrument_id"]
    assert counts(session_factory)[0:3] == [1, 1, 1]
    assert counts(session_factory)[-1] == 1


def test_registry_same_issuer_multiple_classes_not_same_instrument(session_factory):
    repository = SecurityRegistryRepository(session_factory)
    repository.import_snapshot([record("ZZQA", share_class="A"), record("ZZQB", share_class="B")], PROVENANCE)
    a, b = repository.resolve("ZZQA"), repository.resolve("ZZQB")
    assert a["issuer_id"] == b["issuer_id"]
    assert a["instrument_id"] != b["instrument_id"]


def test_registry_alias_is_explicit_and_not_mechanical_dot_hyphen(session_factory):
    repository = SecurityRegistryRepository(session_factory)
    repository.import_snapshot([record("ZZQ-B", symbol_aliases=["ZZQ.B"], aliases=["Synthetic Quantum"], provider_symbols={"fmp": "ZZQ-B"})], PROVENANCE)
    assert repository.resolve("zzq.b")["ticker"] == "ZZQ-B"
    assert repository.resolve("ZZQ-B")["provider_symbols"] == {"fmp": "ZZQ-B"}
    assert repository.search("synthetic quantum")["results"][0]["ticker"] == "ZZQ-B"
    repository.import_snapshot([record("ZZX-B", cik="0000000002")], PROVENANCE)
    with pytest.raises(ApiError, match="No security") as exc:
        repository.resolve("ZZX.B")
    assert exc.value.code == "unknown_ticker"


def test_company_alias_is_search_only_even_when_it_looks_like_a_ticker(session_factory):
    repository = SecurityRegistryRepository(session_factory)
    repository.import_snapshot([record("ZZQA", aliases=["QUANTUM", "Big Blue Research"], symbol_aliases=["ZZQ.A"])], PROVENANCE)
    assert repository.search("QUANTUM")["results"][0]["ticker"] == "ZZQA"
    assert repository.search("blue research")["results"][0]["ticker"] == "ZZQA"
    with pytest.raises(ApiError) as exc:
        repository.resolve("QUANTUM")
    assert exc.value.code == "unknown_ticker"
    selected = repository.resolve("ZZQ.A")
    assert selected["symbol_aliases"] == ["ZZQ.A"]
    assert selected["aliases"] == ["Big Blue Research", "QUANTUM"]
    search_row = repository.search("ZZQ.A")["results"][0]
    assert search_row["symbol_aliases"] == ["ZZQ.A"]


@pytest.mark.parametrize("symbol_aliases", [["Company Name"], ["INVALID/SYMBOL"], [""]])
def test_security_symbol_alias_syntax_is_validated(session_factory, symbol_aliases):
    repository = SecurityRegistryRepository(session_factory)
    with pytest.raises(ValueError):
        repository.import_snapshot([record(symbol_aliases=symbol_aliases)], PROVENANCE)
    assert counts(session_factory) == [0, 0, 0, 0, 0]


def test_symbol_aliases_require_source_references_even_for_unverified_identity(session_factory):
    repository = SecurityRegistryRepository(session_factory)
    with pytest.raises(ValueError, match="source references"):
        repository.import_snapshot([record(identity_status="reference_only", source_refs=[], symbol_aliases=["ZZQ.A"])], PROVENANCE)
    assert counts(session_factory) == [0, 0, 0, 0, 0]


def test_registry_ticker_reuse_requires_explicit_selection_and_preserves_issuer(session_factory):
    repository = SecurityRegistryRepository(session_factory)
    repository.import_snapshot([record()], PROVENANCE)
    old = repository.resolve("ZZQA")
    repository.import_snapshot([record(cik="0000000002", name="Synthetic New Issuer")], {**PROVENANCE, "as_of": "2026-10-19"})
    with pytest.raises(ApiError) as exc:
        repository.resolve("ZZQA")
    assert exc.value.code == "identity_ambiguous"
    assert len(exc.value.details["candidates"]) == 2
    selected = repository.resolve("ZZQA", old["instrument_id"])
    assert selected["cik"] == "0000000001" and selected["symbol_reassigned"] is True
    assert counts(session_factory)[0:3] == [2, 2, 2]


def test_same_issuer_different_security_reuse_requires_verified_history_interval(session_factory):
    from app.services.security_identity import within_listing_period
    repository = SecurityRegistryRepository(session_factory)
    repository.import_snapshot([
        record(instrument_key="prior-security", listing_status="inactive"),
        record(instrument_key="current-security", share_class="Current class"),
    ], PROVENANCE)
    selected = repository.resolve("ZZQA")
    assert selected["symbol_reassigned"] is True
    assert within_listing_period(selected, "2000-01-01") is False
    repository.import_snapshot([
        record(instrument_key="current-security", share_class="Current class", valid_from="2020-01-01")
    ], {**PROVENANCE, "as_of": "2026-10-19"})
    candidates = repository.search("ZZQA")["results"]
    dated = next(row for row in candidates if row["valid_from"] == "2020-01-01")
    selected = repository.resolve("ZZQA", dated["instrument_id"], dated["listing_id"])
    assert within_listing_period(selected, "2000-01-01") is False
    assert within_listing_period(selected, "2020-01-02") is True


def test_listing_selection_disambiguates_venues_and_enforces_both_identifiers(session_factory):
    repository = SecurityRegistryRepository(session_factory)
    repository.import_snapshot([
        record(instrument_key="one-security", exchange="Synthetic Venue One", exchange_mic="XTSA"),
        record(instrument_key="one-security", exchange="Synthetic Venue Two", exchange_mic="XTSB"),
        record("ZZQB", cik="0000000002"),
    ], PROVENANCE)
    candidates = repository.search("ZZQA")["results"]
    assert len(candidates) == 2 and candidates[0]["instrument_id"] == candidates[1]["instrument_id"]
    with pytest.raises(ApiError) as exc:
        repository.resolve("ZZQA", candidates[0]["instrument_id"])
    assert exc.value.code == "identity_ambiguous"
    chosen = candidates[0]
    assert repository.resolve("ZZQA", listing_id=chosen["listing_id"])["listing_id"] == chosen["listing_id"]
    assert repository.resolve("ZZQA", chosen["instrument_id"], chosen["listing_id"])["exchange_mic"] == chosen["exchange_mic"]
    unrelated = repository.resolve("ZZQB")
    with pytest.raises(ApiError) as exc:
        repository.resolve("ZZQA", unrelated["instrument_id"], chosen["listing_id"])
    assert exc.value.code == "unknown_ticker"


@pytest.mark.asyncio
async def test_service_forwards_explicit_listing_selection(session_factory):
    repository = SecurityRegistryRepository(session_factory)
    repository.import_snapshot([
        record(instrument_key="one-security", exchange_mic="XTSA"),
        record(instrument_key="one-security", exchange_mic="XTSB"),
    ], PROVENANCE)
    chosen = repository.search("ZZQA")["results"][0]
    service = SecurityRegistryService(session_factory, SimpleNamespace(registry_bootstrap_enabled=False))
    actual = await service.resolve("ZZQA", chosen["instrument_id"], chosen["listing_id"])
    assert actual["listing_id"] == chosen["listing_id"]


@pytest.mark.asyncio
async def test_old_registry_source_remains_stale_after_recent_retrieval(session_factory, monkeypatch):
    clock = datetime(2026, 10, 18, 12, tzinfo=UTC)
    monkeypatch.setattr("app.registry.service.utcnow", lambda: clock)
    repository = SecurityRegistryRepository(session_factory)
    repository.import_snapshot([record(instrument_type="unknown", listing_status="unknown", identity_status="reference_only")],
                               {**PROVENANCE, "as_of": "2026-10-01", "retrieved_at": clock.isoformat()})
    service = SecurityRegistryService(session_factory, SimpleNamespace(registry_cache_ttl_seconds=86400))
    selected = await service.resolve("ZZQA")
    assert selected["registry_status"] == "stale"
    assert selected["registry_as_of"] == "2026-10-01"
    assert selected["registry_retrieved_at"] == clock.isoformat()
    assert selected["registry_warnings"][0]["code"] == "stale_registry_reference"
    assert selected["instrument_type"] == "unknown" and selected["listing_status"] == "unknown"
    search = await service.search("ZZQA")
    assert search["status"] == "stale" and search["results"][0]["registry_status"] == "stale"
    assert search["warnings"][0]["field"] == "security_registry"


@pytest.mark.asyncio
async def test_current_registry_source_is_fresh_with_actual_retrieval_date(session_factory, monkeypatch):
    clock = datetime(2026, 10, 18, 12, tzinfo=UTC)
    retrieved = datetime(2026, 10, 18, 1, tzinfo=UTC)
    monkeypatch.setattr("app.registry.service.utcnow", lambda: clock)
    repository = SecurityRegistryRepository(session_factory)
    repository.import_snapshot([record()], {**PROVENANCE, "as_of": "2026-10-18", "retrieved_at": retrieved.isoformat()})
    service = SecurityRegistryService(session_factory, SimpleNamespace(registry_cache_ttl_seconds=86400))
    selected = await service.resolve("ZZQA")
    assert selected["registry_status"] == "fresh" and selected["registry_warnings"] == []
    assert selected["registry_retrieved_at"] == retrieved.isoformat()
    search = await service.search("ZZQA")
    assert search["status"] == "fresh" and search["warnings"] == []
    assert search["registry_retrieved_at"] == retrieved.isoformat()


@pytest.mark.asyncio
async def test_search_checks_matched_reference_age_not_only_latest_import(session_factory, monkeypatch):
    clock = datetime(2026, 10, 18, 12, tzinfo=UTC)
    monkeypatch.setattr("app.registry.service.utcnow", lambda: clock)
    repository = SecurityRegistryRepository(session_factory)
    repository.import_snapshot([record()], {**PROVENANCE, "as_of": "2020-01-01"})
    repository.import_snapshot([record("ZZQB", cik="0000000002")], {**PROVENANCE, "as_of": "2026-10-18"})
    service = SecurityRegistryService(session_factory, SimpleNamespace(registry_cache_ttl_seconds=86400))
    search = await service.search("ZZQA")
    assert search["registry_as_of"] == "2026-10-18"
    assert search["results"][0]["registry_as_of"] == "2020-01-01"
    assert search["status"] == "stale"


def test_registry_inactive_old_ticker_and_explicit_rename(session_factory):
    repository = SecurityRegistryRepository(session_factory)
    base = record(instrument_key="stable-security", issuer_key="stable-issuer")
    repository.import_snapshot([base], PROVENANCE)
    old = repository.resolve("ZZQA")
    repository.import_snapshot([{**base, "listing_status": "inactive", "valid_to": "2020-01-01"},
                                {**base, "ticker": "ZZQN", "name": "Synthetic Renamed Issuer"}],
                               {**PROVENANCE, "as_of": "2026-10-19"})
    with pytest.raises(ApiError) as exc:
        repository.resolve("ZZQA", old["instrument_id"])
    assert exc.value.code == "inactive_listing"
    new = repository.resolve("ZZQN")
    assert new["instrument_id"] == old["instrument_id"]
    assert new["listing_id"] != old["listing_id"]
    assert len(repository.search("ZZQ")["results"]) == 2


def test_incomplete_refresh_does_not_delist_omitted_security(session_factory):
    repository = SecurityRegistryRepository(session_factory)
    repository.import_snapshot([record(), record("ZZQB", cik="0000000002")], PROVENANCE)
    repository.import_snapshot([record()], {**PROVENANCE, "as_of": "2026-10-19", "complete_scope": True})
    assert repository.resolve("ZZQB")["listing_status"] == "active"


def test_out_of_order_refresh_preserves_current_classification_and_retains_history(session_factory):
    repository = SecurityRegistryRepository(session_factory)
    repository.import_snapshot([record(name="Current Synthetic Name", instrument_type="insurance")], PROVENANCE)
    repository.import_snapshot([record(name="Older Synthetic Name", instrument_type="unknown")], {**PROVENANCE, "as_of": "2025-01-01"})
    actual = repository.resolve("ZZQA")
    assert actual["name"] == "Current Synthetic Name"
    assert actual["instrument_type"] == "insurance"
    assert counts(session_factory)[-1] == 2


@pytest.mark.parametrize("bad", [
    {"cik": "bad"}, {"instrument_type": "invented"}, {"instrument_type": "common_stock", "classification_evidence": {}},
    {"identity_status": "verified", "source_refs": []}, {"valid_from": "2025-01-01", "valid_to": "2024-01-01"},
    {"api_key": "must-not-be-a-record-field"},
    {"source_refs": [{"api_key": "offline-private-fixture"}]},
    {"source_refs": [{"url": "https://example.invalid/reference?apikey=offline-private-fixture"}]},
])
def test_invalid_registry_import_is_atomic(session_factory, bad):
    repository = SecurityRegistryRepository(session_factory)
    with pytest.raises(ValueError):
        repository.import_snapshot([record(), {**record("ZZQB", cik="0000000002"), **bad}], PROVENANCE)
    assert counts(session_factory) == [0, 0, 0, 0, 0]


def test_conflicting_duplicate_rolls_back_and_cannot_reassign_source_instrument(session_factory):
    repository = SecurityRegistryRepository(session_factory)
    with pytest.raises(ValueError, match="Conflicting"):
        repository.import_snapshot([record(), record(name="Contradiction")], PROVENANCE)
    assert counts(session_factory)[-1] == 0
    repository.import_snapshot([record(instrument_key="immutable", issuer_key="issuer-one")], PROVENANCE)
    with pytest.raises(ValueError, match="reassigned"):
        repository.import_snapshot([record(cik="0000000002", instrument_key="immutable", issuer_key="issuer-two")],
                                   {**PROVENANCE, "as_of": "2026-10-19"})
    assert repository.resolve("ZZQA")["cik"] == "0000000001"


def test_missing_cik_still_searchable_and_not_merged_by_name(session_factory):
    repository = SecurityRegistryRepository(session_factory)
    repository.import_snapshot([record(cik=None), record("ZZQB", cik=None)], PROVENANCE)
    assert repository.resolve("ZZQA")["cik"] is None
    assert counts(session_factory)[0:3] == [2, 2, 2]


def test_ranking_pagination_empty_query_and_unknown(session_factory):
    repository = SecurityRegistryRepository(session_factory)
    repository.import_snapshot([record("ZZQA"), record("ZZQAA", cik="0000000002"),
                                record("ZZQB", cik="0000000003", symbol_aliases=["ZZQ"])], PROVENANCE)
    results = repository.search("ZZQ", 1)
    assert results["results"][0]["ticker"] == "ZZQB"  # Exact source alias precedes prefix.
    assert results["has_more"] is True
    assert repository.search("ZZQ", 1, 1)["results"][0]["ticker"] == "ZZQA"
    assert repository.search("zzqa")["results"][0]["ticker"] == "ZZQA"
    assert repository.search("%")["results"] == []
    assert repository.search("")["results"] == []
    assert repository.search("missing")["results"] == []
    with pytest.raises(ApiError) as exc:
        repository.resolve("ZZNONE")
    assert exc.value.code == "unknown_ticker"


def test_sec_reference_parser_does_not_invent_security_class_or_listing_status():
    rows = sec_reference_records({"fields": ["cik", "name", "ticker", "exchange"],
                                  "data": [[1, "Synthetic Issuer", "ZZQA", "Nasdaq"]]})
    assert rows[0]["instrument_type"] == "unknown"
    assert rows[0]["listing_status"] == "unknown"
    assert rows[0]["identity_status"] == "reference_only"
    assert rows[0]["cik"] == "0000000001"


@pytest.mark.asyncio
async def test_service_cold_bootstrap_once_and_no_provider_per_keystroke(session_factory):
    class Sec:
        calls = 0
        async def security_directory(self):
            self.calls += 1
            return {"records": [record()], "provenance": PROVENANCE}
    sec = Sec()
    service = SecurityRegistryService(session_factory, SimpleNamespace(registry_bootstrap_enabled=True), sec=sec)
    responses = await asyncio.gather(*(service.search("ZZQ") for _ in range(10)))
    assert sec.calls == 1
    assert all(row["results"] for row in responses)
    assert (await service.resolve("ZZQA"))["cik"] == "0000000001"


@pytest.mark.asyncio
async def test_legacy_fake_provider_has_explicit_empty_registry(session_factory):
    service = SecurityRegistryService(session_factory, object(), sec=object())
    assert (await service.search("ZZQ"))["registry_empty"] is True
    with pytest.raises(ApiError) as exc:
        await service.resolve("ZZQA")
    assert exc.value.code == "registry_empty"


@pytest.mark.asyncio
async def test_bootstrap_disabled_does_not_make_directory_request(session_factory):
    class Sec:
        async def security_directory(self):
            pytest.fail("Disabled registry bootstrap must not call a provider.")
    service = SecurityRegistryService(session_factory, SimpleNamespace(registry_bootstrap_enabled=False), sec=Sec())
    assert (await service.search("ZZQ"))["registry_empty"]


@pytest.mark.asyncio
async def test_bootstrap_uses_persistent_reference_cache(session_factory):
    from app.services.cache_service import CacheService
    class Sec:
        async def security_directory(self):
            pytest.fail("A fresh persistent reference cache must prevent network access.")
    cache = CacheService(session_factory)
    cache._write("security-registry:sec-reference:v1", {"records": [record()], "provenance": PROVENANCE}, 86400, "sec-edgar")
    service = SecurityRegistryService(session_factory, SimpleNamespace(registry_bootstrap_enabled=True), sec=Sec(), cache=cache)
    assert (await service.search("ZZQ"))["results"][0]["ticker"] == "ZZQA"


@pytest.mark.asyncio
async def test_failed_bootstrap_has_cooldown_and_can_recover(session_factory):
    from app.providers.base import ProviderError
    class Sec:
        calls = 0
        async def security_directory(self):
            self.calls += 1
            if self.calls == 1:
                raise ProviderError("provider_unavailable", "Offline simulated provider failure.")
            return {"records": [record()], "provenance": PROVENANCE}
    sec = Sec()
    service = SecurityRegistryService(session_factory, SimpleNamespace(registry_bootstrap_enabled=True), sec=sec)
    with pytest.raises(ProviderError):
        await service.search("ZZQ")
    assert (await service.search("ZZQ"))["registry_empty"]
    assert sec.calls == 1
    service._bootstrap_failure_at -= 61
    assert (await service.search("ZZQ"))["results"]
    assert sec.calls == 2


def test_registry_migration_roundtrip_preserves_existing_tables(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'registry.sqlite'}")
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        command.check(config)
        assert "security_listings" in inspect(connection).get_table_names()
        command.downgrade(config, "0001_financial_data")
        tables = set(inspect(connection).get_table_names())
        assert "security_listings" not in tables and "companies" in tables and "financial_facts" in tables
    engine.dispose()


def test_in_memory_registry_import_respects_foreign_key_ordering():
    from app.core.database import Base, build_session_factory
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    @event.listens_for(engine, "connect")
    def enforce_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")
    try:
        Base.metadata.create_all(engine)
        factory = build_session_factory(engine)
        repository = SecurityRegistryRepository(factory)
        repository.import_snapshot([record(), record("ZZQB", share_class="B")], PROVENANCE)
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        assert counts(factory)[0:3] == [1, 2, 2]
    finally:
        engine.dispose()


def test_ten_thousand_synthetic_registry_bounded_search(session_factory):
    repository = SecurityRegistryRepository(session_factory)
    rows = [record(f"ZS{index:05d}", cik=str(index + 1), name=f"Synthetic Sector{index % 20} Issuer {index:05d}")
            for index in range(10000)]
    started = time.perf_counter()
    repository.import_snapshot(rows, PROVENANCE)
    imported = time.perf_counter() - started
    started = time.perf_counter()
    exact = repository.search("ZS05000")
    named = repository.search("sector12", 10, 10)
    prefix = repository.search("ZS05", 10)
    elapsed = time.perf_counter() - started
    assert exact["results"][0]["ticker"] == "ZS05000"
    assert len(named["results"]) == 10 and named["has_more"]
    assert len(prefix["results"]) == 10 and prefix["has_more"]
    assert counts(session_factory)[0:3] == [10000, 10000, 10000]
    print(f"Synthetic 10000-row SQLite import={imported:.3f}s; three bounded searches={elapsed:.3f}s")
