"""Offline free-plan permissions and persisted denial/budget isolation."""
import asyncio
from datetime import UTC, datetime

import httpx
import pytest

from app.core.config import Settings
from app.providers.base import ProviderError
from app.providers.market_data import FmpMarketDataProvider
from app.services.cache_service import CacheService
from app.services.market_access import market_access_call


def configuration(**changes):
    return Settings(_env_file=None, **changes)


def provider(handler):
    return FmpMarketDataProvider(httpx.AsyncClient(transport=httpx.MockTransport(handler)), api_key="offline-fixture", min_interval=0)


def quote(symbol="AAPL"):
    return [{"symbol": symbol, "currency": "USD", "exchange": "NASDAQ", "price": 100,
             "timestamp": datetime.now(UTC).timestamp()}]


def test_no_configured_permission_means_no_http(session_factory):
    calls = []
    market = provider(lambda request: calls.append(request) or httpx.Response(200, json=quote()))
    with pytest.raises(ProviderError, match="explicitly configured"):
        asyncio.run(market_access_call(market, CacheService(session_factory), configuration(), "quote", {"ticker": "AAPL"}))
    assert calls == []


@pytest.mark.parametrize("status,code", [(402, "provider_subscription_required"), (401, "provider_access_denied"), (403, "provider_access_denied")])
def test_denial_persists_across_provider_restarts(session_factory, status, code):
    calls = []
    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(status, json={"error": "offline denied"})
    settings = configuration(fmp_authorized_endpoints={"AAPL": ["quote"]})
    cache = CacheService(session_factory)
    for _ in range(2):
        with pytest.raises(ProviderError) as rejected:
            asyncio.run(market_access_call(provider(handler), cache, settings, "quote", {"ticker": "AAPL"}))
        assert rejected.value.code == code
    assert calls == ["/stable/quote"]


def test_budget_shared_by_endpoints_and_instances_and_no_metadata_fallback(session_factory):
    calls = []
    market = provider(lambda request: calls.append(request.url.path) or httpx.Response(200, json=quote()))
    settings = configuration(fmp_authorized_endpoints={"AAPL": ["quote", "profile"]}, fmp_daily_request_budget=1)
    cache = CacheService(session_factory)
    asyncio.run(market_access_call(market, cache, settings, "quote", {"ticker": "AAPL"}))
    with pytest.raises(ProviderError) as exhausted:
        asyncio.run(market_access_call(provider(lambda _: pytest.fail("No second HTTP allowed")), cache, settings, "profile", {"ticker": "AAPL"}))
    assert exhausted.value.code == "market_request_budget_exhausted"
    assert calls == ["/stable/quote"]


def test_valid_cache_needs_no_permission_or_budget(session_factory):
    cache = CacheService(session_factory)
    cache._write("existing-snapshot", {"price": 100}, 100, "fmp")
    market = provider(lambda _: pytest.fail("Valid cached source must not issue HTTP"))
    async def execute():
        return await cache.get_or_load("existing-snapshot", 100, "fmp", lambda: market_access_call(market, cache, configuration(), "quote", {"ticker": "AAPL"}))
    assert asyncio.run(execute()).payload["price"] == 100


def test_rate_limit_is_not_subscription_denial_and_is_not_retried():
    calls = []
    market = provider(lambda request: calls.append(request.url.path) or httpx.Response(429))
    for _ in range(2):
        with pytest.raises(ProviderError) as error:
            asyncio.run(market.quote("AAPL"))
        assert error.value.code == "provider_rate_limited"
    assert calls == ["/stable/quote"]
    assert market.capability("quote", "AAPL")["access_status"] == "rate_limited"


def test_no_implicit_profile_request_when_direct_quote_metadata_is_missing():
    calls = []
    raw = quote()[0]; raw.pop("currency")
    market = provider(lambda request: calls.append(request.url.path) or httpx.Response(200, json=[raw]))
    response = asyncio.run(market.quote("AAPL"))
    assert calls == ["/stable/quote"]
    assert response["price"] == 100 and response["currency"] is None
    assert response["currency_resolution"]["status"] == "quote_currency_unverified"


@pytest.mark.parametrize("scope", [{"*": ["quote"]}, {"AAPL": ["balance-sheet-statement"]}, {"AAPL": ["quote", "quote"]}])
def test_configuration_rejects_wildcard_paid_statement_or_duplicate_scope(scope):
    with pytest.raises(ValueError):
        configuration(fmp_authorized_endpoints=scope)
