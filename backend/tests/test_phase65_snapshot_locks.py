"""Bound lock retention after failed company loads and cancelled waiters."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.core.exceptions import ApiError
from app.services.valuation_service import ValuationService


@pytest.mark.asyncio
async def test_failed_company_loads_do_not_retain_per_security_locks():
    companies = SimpleNamespace(profile=AsyncMock(side_effect=ApiError("provider_unavailable", "Synthetic failure.")))
    financials = SimpleNamespace(dataset=AsyncMock(side_effect=ApiError("missing_cik", "Synthetic missing mapping.")))
    service = ValuationService(companies, financials, Settings(_env_file=None))
    for index in range(150):
        with pytest.raises(ApiError):
            await service.inputs("SYN" + str(index))
    assert service._locks == service._lock_users == service._snapshots == {}


@pytest.mark.asyncio
async def test_cancelled_waiter_preserves_owner_lock_and_releases_final_reference():
    service = ValuationService(None, None, Settings(_env_file=None))
    async with service._key_lock("synthetic"):
        async def wait():
            async with service._key_lock("synthetic"):
                raise AssertionError("Cancelled waiter acquired owner lock.")
        task = asyncio.create_task(wait())
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert service._lock_users == {"synthetic": 1}
    assert service._locks == service._lock_users == {}
