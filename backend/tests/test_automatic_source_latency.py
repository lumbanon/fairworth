"""Optional provider timeouts cannot conceal independent supported valuations."""
import asyncio
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import time
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.core.database import utcnow
from app.providers.base import ProviderError
from app.services.automatic_inputs_service import AutomaticInputsService, EVIDENCE_VERSION
from app.services.cache_service import CacheService
from app.valuation.forecasts import derive_forward_forecasts
from app.valuation.historical_multiples import derive_historical_multiples
from app.valuation.inputs import build_valuation_inputs
from app.valuation.models.forward_pe import calculate


@pytest.fixture
def short_budget(monkeypatch):
    monkeypatch.setattr("app.services.automatic_inputs_service.OPTIONAL_SOURCE_BUDGET_SECONDS", .03)


@pytest.mark.asyncio
async def test_optional_loader_timeout_uses_brief_negative_cache(short_budget, session_factory):
    cache = CacheService(session_factory)
    service = AutomaticInputsService(SimpleNamespace(cache=cache), None, Settings(_env_file=None))
    calls = 0
    async def slow():
        nonlocal calls
        calls += 1
        await asyncio.sleep(10)
    started = time.monotonic()
    result = await service._optional("timeout-test", "fixture", slow)
    assert time.monotonic() - started < 1
    assert result["status"] == "unavailable"
    assert result["error_code"] == "provider_timeout"
    assert (cache._read("timeout-test").expires_at - cache._read("timeout-test").retrieved_at).total_seconds() == 300
    await service._optional("timeout-test", "fixture", slow)
    assert calls == 1


@pytest.mark.asyncio
async def test_history_timeout_preserves_existing_positive_cache_key(short_budget, session_factory):
    cache = CacheService(session_factory)
    async def slow(*args):
        await asyncio.sleep(10)
    market = SimpleNamespace(name="fixture", enabled=True, splits=slow, historical_prices=slow)
    service = AutomaticInputsService(SimpleNamespace(cache=cache, market=market), None, Settings(_env_file=None))
    rows = [{"date": "2025-01-02", "close": 100, "currency": "USD", "adjustment_basis": "split_adjusted", "adjustment_date": "2025-01-02"}]
    key = "market:fixture:prices:MSFT:2000"
    cache._write(key, rows, 1, "fixture", utcnow() - timedelta(hours=1))
    result = await service._prices("MSFT")
    assert result["prices"] == rows
    assert result["status"] == "stale"
    assert result["warnings"][0]["code"] == "stale_provider_failure"
    assert cache._read(key).payload == rows


@pytest.mark.asyncio
async def test_treasury_stale_status_dates_and_warnings_survive_timeout(short_budget, session_factory):
    cache = CacheService(session_factory)
    async def slow():
        await asyncio.sleep(10)
    treasury = SimpleNamespace(name="us-treasury", risk_free_rate=slow)
    service = AutomaticInputsService(SimpleNamespace(cache=cache), None, Settings(_env_file=None), treasury)
    observed = (utcnow() - timedelta(days=1)).date().isoformat()
    record = {"value": .04, "observation_date": observed, "unit": "fraction", "state": "verified_value", "warnings": []}
    key = f"treasury:10year:{datetime.now(UTC).date().isoformat()}:v{EVIDENCE_VERSION}"
    cache._write(key, {"available": True, "data": record}, 1, "us-treasury", utcnow() - timedelta(hours=1))
    result = await service._treasury()
    assert result["value"] == .04
    assert result["observation_date"] == observed
    assert result["status"] == "stale"
    assert any("stale" in warning and "provider_timeout" in warning for warning in result["warnings"])


@pytest.mark.asyncio
async def test_beta_stale_signed_observation_preserves_warning_and_original_date(short_budget, session_factory):
    cache = CacheService(session_factory)
    async def slow(ticker):
        await asyncio.sleep(10)
    market = SimpleNamespace(name="fmp", enabled=True, profile=slow)
    service = AutomaticInputsService(SimpleNamespace(cache=cache, market=market), None, Settings(_env_file=None))
    retrieved = utcnow() - timedelta(days=2)
    cache._write("market:fmp:profile:MSFT", {"beta": -.2, "beta_methodology": "Provider estimate."}, 1, "fmp", retrieved)
    result = await service._beta("MSFT")
    assert result["value"] == -.2
    assert result["observation_date"] == retrieved.date().isoformat()
    assert result["status"] == "stale"
    assert any("stale" in warning and "provider_timeout" in warning for warning in result["warnings"])
    assert any("not a separately supplied calculation date" in warning for warning in result["warnings"])


@pytest.mark.asyncio
async def test_entire_optional_loader_respects_smaller_configured_timeout():
    settings = Settings(_env_file=None, provider_timeout_seconds=1)
    service = AutomaticInputsService(SimpleNamespace(cache=None), None, settings)
    cancelled = False
    async def slow():
        nonlocal cancelled
        try:
            await asyncio.sleep(10)
        finally:
            cancelled = True
    started = time.monotonic()
    with pytest.raises(ProviderError) as captured:
        await service._bounded(slow)
    assert captured.value.code == "provider_timeout"
    assert cancelled is True
    assert time.monotonic() - started < 2  # configured one-second bound, not the three-second ceiling.


@pytest.mark.asyncio
async def test_treasury_and_statements_timeout_independently_while_pe_survives(short_budget, session_factory):
    fixtures = Path(__file__).parent / "fixtures" / "valuation"
    old = json.loads((fixtures / "verified_provider_excerpts.json").read_text())["companies"]["AAPL"]
    actual = json.loads((fixtures / "automatic_evidence_excerpts.json").read_text())["companies"]["AAPL"]["evidence"]
    cache = CacheService(session_factory)
    started_statements = []
    async def prices(*args):
        return actual["historical_prices"]["prices"]
    async def splits(*args):
        return actual["splits"]["splits"]
    async def profile(*args):
        return {"beta": 1.1, "beta_methodology": "Deterministic provider estimate."}
    async def statements(ticker, kind):
        started_statements.append(kind)
        # Both statements must start before either timeout completes.
        await asyncio.sleep(.001)
        assert len(started_statements) == 2
        await asyncio.sleep(10)
    async def treasury():
        await asyncio.sleep(10)
    market = SimpleNamespace(name="fixture", enabled=True, historical_prices=prices, splits=splits, profile=profile, financial_statements=statements)
    companies = SimpleNamespace(cache=cache, market=market)
    settings = Settings(_env_file=None)
    service = AutomaticInputsService(companies, None, settings, SimpleNamespace(name="us-treasury", risk_free_rate=treasury))
    cik = old["profile"]["company"]["cik"]
    retrieved = cache._write(f"sec:facts:{cik}", {"facts": {}}, 3600, "sec-edgar")
    cache._write(f"sec:annual-publications:{cik}:AAPL:{retrieved.isoformat()}:v{EVIDENCE_VERSION}", actual["historical_annual_periods"], 3600, "sec-edgar")
    started = time.monotonic()
    result = await service.evidence("AAPL", old["profile"], old["normalized"], old["retrieved_at"])
    assert time.monotonic() - started < 1
    assert result["historical_prices"]["prices"]
    assert result["splits"]["complete"] is True
    assert result["observations"]["risk_free_rate"]["value"] is None
    assert all(row["error_code"] == "provider_timeout" for row in result["supplemental_statements"].values())
    inputs = build_valuation_inputs(old["profile"], old["normalized"], old["retrieved_at"])
    multiple = derive_historical_multiples(inputs, result)["assumptions"]["target_pe"]["value"]
    eps = derive_forward_forecasts(inputs, result)["assumptions"]["forward_eps"]["value"]
    assert calculate({"forward_eps": eps, "target_pe": multiple})["fair_value"] > 0
