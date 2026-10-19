"""Issuer-symbol and exchange-listing clocks remain independent (synthetic)."""
from copy import deepcopy
from datetime import datetime, UTC
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.providers.base import ProviderError
from app.registry.importers import sec_reference_records
from app.registry.repository import SecurityRegistryRepository
from app.registry.service import SecurityRegistryService
from app.services.cache_service import CacheService
from app.services.company_service import CompanyService
from app.services.security_identity import cache_scope
from test_verified_listing_registry import SEC, bundle, publish, sec


def setup_sources(session_factory, monkeypatch, *, listing_date="1020202607:00"):
    import app.registry.service as module
    monkeypatch.setattr(module, "utcnow", lambda: datetime(2026, 10, 20, 12, tzinfo=UTC))
    repository = SecurityRegistryRepository(session_factory)
    sec(repository)
    publish(repository, bundle("ZZQA|Synthetic Alpha - Common Stock|Q|N|N|100|N|N", footer=listing_date))
    settings = SimpleNamespace(registry_cache_ttl_seconds=86400, registry_bootstrap_enabled=False,
                               company_cache_ttl_seconds=300)
    return repository, SecurityRegistryService(session_factory, settings), settings


@pytest.mark.asyncio
async def test_fresh_listing_does_not_refresh_old_issuer_mapping_or_profile_failure(session_factory, monkeypatch):
    repository, registry, settings = setup_sources(session_factory, monkeypatch)
    stored = repository.resolve("ZZQA")
    selected = await registry.resolve("ZZQA")
    assert selected["registry_as_of"] == "2026-10-20"
    assert selected["registry_status"] == "fresh"
    assert selected["listing_verification"]["status"] == "verified"
    assert selected["issuer_linkage"]["observed_on"] == "2026-10-18"
    assert selected["issuer_linkage"]["freshness"] == "stale"
    assert selected["identity_status"] == "reference_only"
    assert selected["instrument_id"] == stored["instrument_id"]
    sec_provider = SimpleNamespace(company_for_identity=AsyncMock(side_effect=ProviderError(
        "provider_timeout", "Synthetic provider unavailable.", 503)))
    companies = CompanyService(sec_provider, None, CacheService(session_factory), None, settings, registry)
    company, result = await companies.company_identity("ZZQA")
    assert company["identity_status"] == "reference_only"
    assert any(item["code"] == "stale_issuer_symbol_reference" for item in result.warnings)
    sec_provider.company_for_identity.assert_awaited_once()


@pytest.mark.asyncio
async def test_explicit_sec_refresh_updates_ownership_clock_without_refreshing_listing(session_factory, monkeypatch):
    repository, registry, _ = setup_sources(session_factory, monkeypatch, listing_date="1019202607:00")
    previous = await registry.resolve("ZZQA")
    rows = sec_reference_records({"fields": ["cik", "name", "ticker", "exchange"],
        "data": [[1, "Synthetic Alpha", "ZZQA", "Nasdaq"]]})
    repository.import_snapshot(rows, {**SEC, "as_of": "2026-10-20"})
    selected = await registry.resolve("ZZQA")
    assert selected["issuer_linkage"]["observed_on"] == "2026-10-20"
    assert selected["issuer_linkage"]["freshness"] == "fresh"
    assert selected["identity_status"] == "verified"
    assert selected["listing_verification"]["observed_on"] == "2026-10-19"
    assert selected["listing_verification"]["stale"] is True
    assert selected["registry_status"] == "stale"
    assert selected["instrument_id"] == previous["instrument_id"]
    assert cache_scope(selected) != cache_scope(previous)


@pytest.mark.parametrize("mutation", ["missing", "future", "wrong_cik", "wrong_issuer", "wrong_venue"])
def test_unverified_issuer_linkage_cannot_promote_current_ownership(session_factory, monkeypatch, mutation):
    repository, registry, _ = setup_sources(session_factory, monkeypatch)
    identity = deepcopy(repository.resolve("ZZQA"))
    linkage = identity["listing_verification"]["issuer_linkage"]
    linkage["observed_on"] = "2026-10-20"
    if mutation == "missing":
        identity["listing_verification"]["issuer_linkage"] = None
        identity["issuer_linkage"] = {}
    elif mutation == "future":
        linkage["observed_on"] = "2026-10-21"
    else:
        linkage[{"wrong_cik": "cik", "wrong_issuer": "issuer_id", "wrong_venue": "exchange_mic"}[mutation]] = "wrong"
    selected = registry._with_freshness(identity)
    assert selected["identity_status"] == "reference_only"
    assert selected["listing_verification"]["status"] == "verified"
    assert any(item["field"] == "issuer_linkage" for item in selected["registry_warnings"])
