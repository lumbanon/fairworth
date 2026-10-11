from datetime import timedelta

import pytest

from app.core.database import utcnow
from app.models import CacheEntry
from app.providers.base import ProviderError
from app.services.cache_service import CacheService


@pytest.mark.asyncio
async def test_cache_reuses_fresh_data_and_marks_failure_fallback_stale(session_factory):
    cache = CacheService(session_factory)
    calls = 0

    async def load():
        nonlocal calls
        calls += 1
        return {"price": 100}

    first = await cache.get_or_load("quote", 300, "fixture", load)
    assert (await cache.get_or_load("quote", 300, "fixture", load)).payload == first.payload
    assert calls == 1
    with session_factory.begin() as session:
        session.get(CacheEntry, "quote").expires_at = utcnow() - timedelta(seconds=1)

    async def fail():
        raise ProviderError("provider_timeout", "The provider timed out.", 503)

    stale = await cache.get_or_load("quote", 300, "fixture", fail)
    assert stale.status == "stale"
    assert stale.payload == {"price": 100}
    assert stale.retrieved_at == first.retrieved_at
    assert stale.warnings[0]["code"] == "stale_provider_failure"


@pytest.mark.asyncio
async def test_no_cache_does_not_invent_data(session_factory):
    async def fail():
        raise ProviderError("provider_disabled", "No provider configured.", 503)

    with pytest.raises(ProviderError):
        await CacheService(session_factory).get_or_load("unknown", 1, "fixture", fail)


@pytest.mark.asyncio
async def test_concurrent_refresh_only_loads_once(session_factory):
    import asyncio
    cache = CacheService(session_factory)
    calls = 0

    async def load():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return {"price": 100}

    results = await asyncio.gather(*(cache.get_or_load("shared", 10, "fixture", load) for _ in range(5)))
    assert calls == 1
    assert all(result.status == "fresh" for result in results)
