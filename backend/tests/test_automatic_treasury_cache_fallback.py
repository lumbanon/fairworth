"""A new day must not erase recent, explicitly dated Treasury observations."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.core.database import utcnow
from app.services.automatic_inputs_service import AutomaticInputsService, PROVIDER_CACHE_VERSION
from app.services.cache_service import CacheService


def key(day):
    return f"treasury:10year:{day.isoformat()}:v{PROVIDER_CACHE_VERSION}"


def fixture_service(session_factory):
    cache = CacheService(session_factory)
    async def unexpected_network_call():
        pytest.fail("A fresh negative cache must prevent another provider call.")
    treasury = SimpleNamespace(name="us-treasury", risk_free_rate=unexpected_network_call)
    service = AutomaticInputsService(SimpleNamespace(cache=cache), None, Settings(_env_file=None), treasury)
    today = datetime.now(UTC).date()
    failure = {"available": False, "error_code": "provider_timeout", "message": "The optional source exceeded its time budget."}
    cache._write(key(today), failure, 300, "us-treasury")
    return service, cache, today


def seed(cache, cache_day, observation_day, *, value=.04, state="verified_value", unit="fraction", provider="us-treasury"):
    retrieved = datetime.combine(cache_day, datetime.min.time(), tzinfo=UTC) + timedelta(hours=12)
    record = {"value": value, "unit": unit, "state": state, "observation_date": observation_day.isoformat(),
              "retrieved_at": retrieved.isoformat(), "provider": provider, "source_provider": provider,
              "source_type": "market_observation", "kind": "fact", "warnings": ["Original source warning."]}
    # Keep the provider's retrieval instant distinct from the SQL cache write.
    cache._write(key(cache_day), {"available": True, "data": record}, 1, provider, retrieved + timedelta(seconds=1))
    return record


@pytest.mark.asyncio
async def test_prior_day_fallback_retains_original_dates_failure_warning_and_cache_contents(session_factory):
    service, cache, today = fixture_service(session_factory)
    yesterday = today - timedelta(days=1)
    original = seed(cache, yesterday, yesterday)
    old_entry = cache._read(key(yesterday))
    before = deepcopy(old_entry.payload)
    negative = deepcopy(cache._read(key(today)).payload)
    result = await service._treasury()
    assert result["value"] == .04
    assert result["observation_date"] == yesterday.isoformat()
    assert result["retrieved_at"] == original["retrieved_at"]
    assert result["source_id"] == key(yesterday)
    assert result["status"] == "stale"
    assert "Original source warning." in result["warnings"]
    assert any("provider_timeout" in warning and "current-day refresh" in warning for warning in result["warnings"])
    assert cache._read(key(yesterday)).payload == before
    assert cache._read(key(yesterday)).expires_at == old_entry.expires_at
    assert cache._read(key(today)).payload == negative


@pytest.mark.asyncio
async def test_fallback_prefers_latest_observation_rather_than_latest_cache_key(session_factory):
    service, cache, today = fixture_service(session_factory)
    seed(cache, today - timedelta(days=1), today - timedelta(days=4), value=.03)
    freshest = seed(cache, today - timedelta(days=2), today - timedelta(days=2), value=.045)
    result = await service._treasury()
    assert result["value"] == .045
    assert result["observation_date"] == freshest["observation_date"]
    assert result["retrieved_at"] == freshest["retrieved_at"]


@pytest.mark.asyncio
async def test_fallback_accepts_seven_day_boundary_but_not_older_yields(session_factory):
    service, cache, today = fixture_service(session_factory)
    seed(cache, today - timedelta(days=1), today - timedelta(days=8))
    assert (await service._treasury())["value"] is None
    accepted = seed(cache, today - timedelta(days=2), today - timedelta(days=7), value=.05)
    result = await service._treasury()
    assert result["value"] == .05
    assert result["observation_date"] == accepted["observation_date"]


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [
    {"value": None}, {"value": True}, {"value": .4}, {"value": -.06}, {"unit": "percent"},
    {"state": "unknown"}, {"state": "verified_zero"}, {"provider": "unverified-source"},
])
async def test_invalid_or_unknown_prior_records_cannot_supply_a_fallback(session_factory, changes):
    service, cache, today = fixture_service(session_factory)
    seed(cache, today - timedelta(days=1), today - timedelta(days=1), **changes)
    result = await service._treasury()
    assert result["value"] is None
    assert result["status"] == "unavailable"
    assert "provider_timeout" in result["warnings"]


@pytest.mark.asyncio
async def test_future_observation_cannot_be_borrowed_from_an_older_cache_key(session_factory):
    service, cache, today = fixture_service(session_factory)
    seed(cache, today - timedelta(days=1), today + timedelta(days=1))
    assert (await service._treasury())["value"] is None


@pytest.mark.asyncio
async def test_verified_zero_yield_is_preserved_instead_of_treated_as_missing(session_factory):
    service, cache, today = fixture_service(session_factory)
    original = seed(cache, today - timedelta(days=1), today - timedelta(days=1), value=0, state="verified_zero")
    result = await service._treasury()
    assert result["value"] == 0
    assert result["state"] == "verified_zero"
    assert result["status"] == "stale"
    assert result["retrieved_at"] == original["retrieved_at"]


@pytest.mark.asyncio
async def test_current_success_keeps_its_source_and_does_not_use_stale_fallback(session_factory):
    service, cache, today = fixture_service(session_factory)
    seed(cache, today - timedelta(days=1), today - timedelta(days=1), value=.03)
    now = utcnow()
    current = {"value": .05, "unit": "fraction", "state": "verified_value", "observation_date": today.isoformat(), "warnings": []}
    cache._write(key(today), {"available": True, "data": current}, 300, "us-treasury", now)
    result = await service._treasury()
    assert result["value"] == .05
    assert result["observation_date"] == today.isoformat()
    assert result["source_id"] == key(today)
    assert result["status"] == "fresh"
    assert result["warnings"] == []
