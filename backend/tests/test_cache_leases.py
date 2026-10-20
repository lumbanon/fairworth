"""Cross-worker refresh coordination with synthetic loaders, no provider calls."""
import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.core.database import utcnow
from app.models import CacheEntry
from app.providers.base import ProviderError
from app.services.cache_service import CacheService, CachedResult


def leases(factory):
    with factory() as session:
        return session.scalar(select(func.count()).select_from(CacheEntry).where(CacheEntry.provider == "fairworth-cache-lease"))


@pytest.mark.asyncio
async def test_two_cache_instances_share_one_expensive_load(session_factory):
    caches = [CacheService(session_factory), CacheService(session_factory)]
    calls = 0
    async def load():
        nonlocal calls
        calls += 1
        await asyncio.sleep(.03)
        return {"public": "one observation"}
    responses = await asyncio.gather(*(caches[index % 2].get_or_load("shared", 300, "fixture", load) for index in range(12)))
    assert calls == 1
    assert all(row.payload == responses[0].payload for row in responses)
    assert leases(session_factory) == 0
    assert all(cache._locks == cache._lock_users == {} for cache in caches)


@pytest.mark.asyncio
async def test_distinct_and_nested_keys_do_not_serialize_or_deadlock(session_factory):
    cache = CacheService(session_factory)
    a, b = asyncio.Event(), asyncio.Event()
    async def first():
        a.set()
        await asyncio.wait_for(b.wait(), 1)
        return {"first": True}
    async def second():
        b.set()
        await asyncio.wait_for(a.wait(), 1)
        return {"second": True}
    await asyncio.gather(cache.get_or_load("a", 300, "fixture", first), cache.get_or_load("b", 300, "fixture", second))
    async def inner():
        return {"nested": True}
    async def outer():
        result = await cache.get_or_load("inner", 300, "fixture", inner)
        return result.payload
    assert (await cache.get_or_load("outer", 300, "fixture", outer)).payload == {"nested": True}
    assert leases(session_factory) == 0


@pytest.mark.asyncio
async def test_expired_crashed_owner_lease_can_be_recovered(session_factory):
    cache = CacheService(session_factory)
    cache._write(cache._lease_key("crashed"), {"owner": "crashed-worker"}, 1, "fairworth-cache-lease",
                 utcnow() - timedelta(seconds=5))
    async def load():
        return {"recovered": True}
    assert (await cache.get_or_load("crashed", 300, "fixture", load)).payload["recovered"]
    assert leases(session_factory) == 0


@pytest.mark.asyncio
async def test_long_loader_renews_lease_and_prevents_second_instance_load(session_factory):
    one = CacheService(session_factory, lease_seconds=.12, wait_seconds=1, poll_seconds=.01)
    two = CacheService(session_factory, lease_seconds=.12, wait_seconds=1, poll_seconds=.01)
    calls = 0
    async def load():
        nonlocal calls
        calls += 1
        await asyncio.sleep(.35)
        return {"complete": True}
    first = asyncio.create_task(one.get_or_load("long", 300, "fixture", load))
    await asyncio.sleep(.18)
    second = asyncio.create_task(two.get_or_load("long", 300, "fixture", load))
    assert all(row.payload["complete"] for row in await asyncio.gather(first, second))
    assert calls == 1
    assert leases(session_factory) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("same_instance", [False, True])
@pytest.mark.parametrize("has_stale", [False, True])
async def test_wait_timeout_is_explicit_or_returns_original_stale_data(session_factory, same_instance, has_stale):
    one = CacheService(session_factory, wait_seconds=.05, poll_seconds=.005)
    two = one if same_instance else CacheService(session_factory, wait_seconds=.05, poll_seconds=.005)
    started, finish = asyncio.Event(), asyncio.Event()
    if has_stale:
        one._write("busy", {"old": True}, 1, "fixture", utcnow() - timedelta(seconds=5))
    async def load():
        started.set()
        await finish.wait()
        return {"new": True}
    active = asyncio.create_task(one.get_or_load("busy", 300, "fixture", load))
    await started.wait()
    try:
        if has_stale:
            result = await two.get_or_load("busy", 300, "fixture", load)
            assert result.status == "stale" and result.payload == {"old": True}
            assert "cache_refresh_busy" in result.warnings[0]["message"]
        else:
            with pytest.raises(ProviderError) as exc:
                await two.get_or_load("busy", 300, "fixture", load)
            assert exc.value.code == "cache_refresh_busy" and exc.value.retryable
    finally:
        finish.set()
        await active
    assert leases(session_factory) == 0 and one._locks == two._locks == {}


@pytest.mark.asyncio
async def test_cancelled_owner_releases_lease_and_cancels_loader(session_factory):
    cache = CacheService(session_factory)
    started, cancelled = asyncio.Event(), asyncio.Event()
    async def load():
        started.set()
        try:
            await asyncio.sleep(30)
        finally:
            cancelled.set()
    task = asyncio.create_task(cache.get_or_load("cancelled", 300, "fixture", load))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled.is_set() and leases(session_factory) == 0
    assert cache._locks == cache._lock_users == {}


@pytest.mark.asyncio
async def test_cancelled_waiter_does_not_leak_local_lock_reference(session_factory):
    cache = CacheService(session_factory)
    started, finish = asyncio.Event(), asyncio.Event()
    async def load():
        started.set()
        await finish.wait()
        return {}
    owner = asyncio.create_task(cache.get_or_load("waiting", 300, "fixture", load))
    await started.wait()
    waiter = asyncio.create_task(cache.get_or_load("waiting", 300, "fixture", load))
    await asyncio.sleep(0)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    finish.set()
    await owner
    assert cache._locks == cache._lock_users == {} and leases(session_factory) == 0


@pytest.mark.asyncio
async def test_provider_failure_releases_lease_and_preserves_data(session_factory):
    cache = CacheService(session_factory)
    async def fail():
        raise ProviderError("provider_subscription_required", "Offline restricted fixture.")
    with pytest.raises(ProviderError):
        await cache.get_or_load("denied", 300, "fixture", fail)
    assert leases(session_factory) == 0 and cache._read("denied") is None
    cache._write("denied", {"old": True}, 1, "fixture", utcnow() - timedelta(seconds=5))
    old = cache._read("denied")
    result = await cache.get_or_load("denied", 300, "fixture", fail)
    assert result.payload == old.payload and result.retrieved_at == old.retrieved_at.replace(tzinfo=result.retrieved_at.tzinfo)
    assert leases(session_factory) == 0


@pytest.mark.asyncio
async def test_lost_ownership_never_overwrites_cache_or_releases_another_owner(session_factory):
    cache = CacheService(session_factory, lease_seconds=.12)
    started, cancelled = asyncio.Event(), asyncio.Event()
    async def load():
        started.set()
        try:
            await asyncio.sleep(30)
        finally:
            cancelled.set()
    task = asyncio.create_task(cache.get_or_load("lost", 300, "fixture", load))
    await started.wait()
    cache._write(cache._lease_key("lost"), {"owner": "another-worker"}, 300, "fairworth-cache-lease")
    with pytest.raises(ProviderError) as exc:
        await task
    assert exc.value.code == "cache_lease_lost"
    assert cancelled.is_set() and cache._read("lost") is None
    assert cache._read(cache._lease_key("lost")).payload["owner"] == "another-worker"


@pytest.mark.asyncio
async def test_many_unique_keys_leave_no_process_lock_or_lease_growth(session_factory):
    cache = CacheService(session_factory)
    async def load():
        return {"bounded": True}
    for index in range(150):
        await cache.get_or_load(f"distinct-{index}", 300, "fixture", load)
    assert cache._locks == cache._lock_users == {} and leases(session_factory) == 0


@pytest.mark.asyncio
async def test_derived_stale_payload_does_not_become_fresh_cache(session_factory):
    cache = CacheService(session_factory)
    observed = utcnow() - timedelta(days=2)
    async def load():
        return CachedResult({"original": True}, "stale", observed, [])
    response = await cache.get_or_load("derived", 300, "fixture", load)
    assert response.status == "stale" and response.retrieved_at == observed
    assert cache._read("derived") is None and leases(session_factory) == 0


def test_publication_checks_ownership_atomically_even_after_successful_renewal(session_factory):
    cache = CacheService(session_factory)
    assert cache._acquire_lease("race", "old")
    assert cache._renew_lease("race", "old")
    cache._write(cache._lease_key("race"), {"owner": "new"}, 300, "fairworth-cache-lease")
    cache._write("race", {"newer": True}, 300, "fixture")
    with pytest.raises(ProviderError) as error:
        cache._write("race", {"older": True}, 300, "fixture", owner="old")
    assert error.value.code == "cache_lease_lost"
    assert cache._read("race").payload == {"newer": True}
