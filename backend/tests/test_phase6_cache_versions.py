"""Changed interpretation must not erase or needlessly reload provider evidence."""
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.services.automatic_inputs_service import AutomaticInputsService, EVIDENCE_VERSION, PROVIDER_CACHE_VERSION
from app.services.cache_service import CacheService
from app.services.normalization import NORMALIZATION_VERSION


@pytest.mark.asyncio
async def test_raw_treasury_split_statement_caches_survive_interpretation_version(session_factory):
    assert EVIDENCE_VERSION == "2.0.0" and PROVIDER_CACHE_VERSION == "1.0.0"
    cache = CacheService(session_factory)
    async def forbidden(*args):
        pytest.fail("Fresh raw evidence must not cause a provider refresh.")
    market = SimpleNamespace(name="fmp", enabled=True, splits=forbidden, financial_statements=forbidden)
    service = AutomaticInputsService(SimpleNamespace(cache=cache, market=market), None, Settings(_env_file=None),
                                     SimpleNamespace(name="us-treasury", risk_free_rate=forbidden))
    today = datetime.now(UTC).date().isoformat()
    yield_record = {"value": .04, "unit": "fraction", "state": "verified_value", "observation_date": today, "warnings": []}
    treasury_key = f"treasury:10year:{today}:v1.0.0"
    cache._write(treasury_key, {"available": True, "data": yield_record}, 3600, "us-treasury")
    cache._write("market:fmp:splits:MSFT:v1.0.0", {"available": True, "data": []}, 3600, "fmp")
    for kind in ("cash_flow", "balance_sheet"):
        cache._write(f"market:fmp:statement:MSFT:{kind}:annual:v1.0.0", {"available": True, "data": []}, 3600, "fmp")
    assert (await service._treasury())["value"] == .04
    assert (await service._splits("MSFT"))["complete"] is True
    statements = await service._supplemental("MSFT")
    assert all(record["available"] for record in statements.values())
    assert cache._read(treasury_key).payload["data"] == yield_record


@pytest.mark.asyncio
async def test_native_annual_interpretation_uses_new_namespace_and_preserves_old(session_factory):
    cache = CacheService(session_factory)
    service = AutomaticInputsService(SimpleNamespace(cache=cache), None, Settings(_env_file=None))
    retrieved = cache._write("sec:facts:0000789019", {"facts": {}}, 3600, "sec-edgar")
    old_key = f"sec:annual-publications:0000789019:MSFT:{retrieved.isoformat()}:v1.0.0"
    cache._write(old_key, [{"legacy": "immutable"}], 3600, "sec-edgar")
    native = AsyncMock(return_value=[{"new": "scoped interpretation"}])
    service._native = native
    service._prices = AsyncMock(return_value={})
    service._splits = AsyncMock(return_value={})
    service._treasury = AsyncMock(return_value={})
    service._beta = AsyncMock(return_value={})
    service._supplemental = AsyncMock(return_value={})
    result = await service.evidence("MSFT", {"company": {"cik": "0000789019"}}, {"annual": []}, retrieved)
    native.assert_awaited_once()
    key = f"sec:annual-publications:0000789019:MSFT:{retrieved.isoformat()}:v{EVIDENCE_VERSION}:n{NORMALIZATION_VERSION}"
    assert cache._read(key).payload == result["historical_annual_periods"] == [{"new": "scoped interpretation"}]
    assert cache._read(old_key).payload == [{"legacy": "immutable"}]
    assert result["normalization_version"] == NORMALIZATION_VERSION
