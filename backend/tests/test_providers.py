"""All provider I/O uses httpx.MockTransport: no SEC contact or key is sent."""

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.providers.base import ProviderError, RateLimiter, normalize_cik
from app.providers.market_data import DisabledMarketDataProvider, FmpMarketDataProvider
from app.providers.sec_edgar import SecEdgarProvider


CONTACT = "Fairworth Offline Test test-contact@example.test"
TICKERS = {
    "0": {"cik_str": 789019, "ticker": "MSFT", "title": "MICROSOFT CORP"},
    "1": {"cik_str": 1652044, "ticker": "GOOG", "title": "ALPHABET INC."},
    "2": {"cik_str": 1067983, "ticker": "BRK-B", "title": "BERKSHIRE HATHAWAY INC"},
}


@pytest.fixture
def no_wait(monkeypatch):
    delays = []

    async def sleep(delay):
        delays.append(delay)

    monkeypatch.setattr("app.providers.base.asyncio.sleep", sleep)
    return delays


@pytest.mark.asyncio
async def test_ticker_mapping_search_company_metadata_and_cache(no_wait):
    requests = []

    def handler(request):
        requests.append(request)
        assert request.headers["User-Agent"] == CONTACT
        if request.url.path == "/files/company_tickers.json":
            return httpx.Response(200, json=TICKERS)
        return httpx.Response(200, json={"name": "MICROSOFT CORPORATION", "tickers": ["MSFT"], "exchanges": ["Nasdaq"], "sic": "7372", "sicDescription": "SERVICES-PREPACKAGED SOFTWARE"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = SecEdgarProvider(client, CONTACT)
        matches = await provider.search("micro", 5)
        assert matches[0] == {"ticker": "MSFT", "name": "MICROSOFT CORP", "cik": "0000789019", "exchange": None}
        assert (await provider.search("MSFT"))[0]["ticker"] == "MSFT"
        company = await provider.company("msft")
        assert company["exchange"] == "Nasdaq"
        assert company["sic"] == "7372"
        assert company["currency"] is None  # Not assumed USD from the exchange.
        assert len([request for request in requests if request.url.path == "/files/company_tickers.json"]) == 1
        assert requests[-1].url.path == "/submissions/CIK0000789019.json"


@pytest.mark.asyncio
async def test_dot_hyphen_share_class_alias_and_bounded_search(no_wait):
    def handler(request):
        if request.url.path == "/files/company_tickers.json":
            return httpx.Response(200, json=TICKERS)
        return httpx.Response(200, json={"name": "BERKSHIRE HATHAWAY INC", "tickers": ["BRK-B"], "exchanges": ["NYSE"]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = SecEdgarProvider(client, CONTACT)
        assert (await provider.search("BRK.B", 1))[0]["ticker"] == "BRK-B"
        assert (await provider.company("BRK.B"))["ticker"] == "BRK-B"
        assert await provider.search("  ") == []


@pytest.mark.asyncio
@pytest.mark.parametrize("ticker,tickers,expected", [
    ("BRK-B", ["BRK-A", "BRK-B"], True),
    ("GOOG", ["GOOG", "GOOGL"], True),
    ("MSFT", ["MSFT"], False),
    ("MSFT", ["MSFT", "msft"], False),
    ("MSFT", None, None),
    ("MSFT", [], None),
])
async def test_sec_profile_marks_unverified_multiple_share_classes(ticker, tickers, expected, no_wait):
    def handler(request):
        if request.url.path == "/files/company_tickers.json":
            return httpx.Response(200, json=TICKERS)
        submission = {"name": "Fixture company", "exchanges": ["TEST"]}
        if tickers is not None:
            submission["tickers"] = tickers
        return httpx.Response(200, json=submission)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        company = await SecEdgarProvider(client, CONTACT).company(ticker)
    assert company["has_multiple_share_classes"] is expected
    assert company["share_class_basis_verified"] is False
    if expected:
        assert company["warnings"][0]["code"] == "share_class_basis_unverified"
    else:
        assert company["warnings"] == []


@pytest.mark.asyncio
async def test_sec_facts_and_submissions_paths_are_padded(no_wait):
    urls = []

    def handler(request):
        urls.append(str(request.url))
        return httpx.Response(200, json={"cik": 1, "facts": {}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = SecEdgarProvider(client, CONTACT)
        assert (await provider.facts(1))["facts"] == {}
        await provider.submissions("1")
    assert urls == ["https://data.sec.gov/api/xbrl/companyfacts/CIK0000000001.json", "https://data.sec.gov/submissions/CIK0000000001.json"]


@pytest.mark.asyncio
@pytest.mark.parametrize("ticker", ["", "../secret", "https://example.com", "MS FT", "ＡＡＰＬ", "ABCDEFGHIJK"])
async def test_invalid_tickers_never_make_requests(ticker):
    def handler(request):
        raise AssertionError("Invalid input must not cause provider I/O")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderError) as captured:
            await SecEdgarProvider(client, CONTACT).company(ticker)
    assert captured.value.code == "invalid_ticker"
    assert captured.value.status_code == 400


@pytest.mark.parametrize("cik", ["0", "", "12345678901", "../1", "１２３", -1])
def test_cik_validation(cik):
    with pytest.raises(ProviderError):
        normalize_cik(cik)


@pytest.mark.asyncio
async def test_unsupported_ticker_is_not_invented():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=TICKERS))) as client:
        with pytest.raises(ProviderError) as captured:
            await SecEdgarProvider(client, CONTACT).company("FAKE")
    assert captured.value.code == "unsupported_ticker"
    assert captured.value.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("contact", ["", "Fairworth", "Fairworth\r\n test@example.com"])
async def test_identifying_contact_is_required_before_sec_access(contact):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: pytest.fail("No configured SEC contact"))) as client:
        with pytest.raises(ProviderError) as captured:
            await SecEdgarProvider(client, contact).facts(1)
    assert captured.value.code == "provider_disabled"


@pytest.mark.asyncio
async def test_rate_limit_retries_respect_retry_after(no_wait):
    count = 0

    def handler(request):
        nonlocal count
        count += 1
        if count == 1:
            return httpx.Response(429, headers={"Retry-After": "2"})
        return httpx.Response(200, json={"facts": {}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await SecEdgarProvider(client, CONTACT, retries=2).facts(1)
    assert result == {"facts": {}}
    assert count == 2
    assert 2 in no_wait


@pytest.mark.asyncio
async def test_timeout_retries_are_bounded_and_safe(no_wait):
    count = 0

    def handler(request):
        nonlocal count
        count += 1
        raise httpx.ReadTimeout("private upstream URL secret-api-key", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderError) as captured:
            await SecEdgarProvider(client, CONTACT, retries=2).facts(1)
    assert count == 3
    assert captured.value.code == "provider_timeout"
    assert captured.value.status_code == 504
    assert "secret" not in str(captured.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("status,code,retryable,expected_requests", [(404, "not_found", False, 1), (403, "provider_access_denied", False, 1), (500, "provider_unavailable", True, 3), (429, "provider_rate_limited", True, 3), (302, "provider_http_error", False, 1)])
async def test_http_errors_and_redirects_are_structured(status, code, retryable, expected_requests, no_wait):
    count = 0

    def handler(request):
        nonlocal count
        count += 1
        return httpx.Response(status, headers={"Location": "https://untrusted.invalid"}, json={"private": "sensitive error"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderError) as captured:
            await SecEdgarProvider(client, CONTACT).facts(1)
    assert captured.value.code == code
    assert captured.value.retryable is retryable
    assert count == expected_requests
    assert "sensitive" not in str(captured.value)


@pytest.mark.asyncio
async def test_malformed_companyfacts_payload_is_rejected():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"name": "missing facts"}))) as client:
        with pytest.raises(ProviderError) as captured:
            await SecEdgarProvider(client, CONTACT).facts(1)
    assert captured.value.code == "invalid_provider_response"


@pytest.mark.asyncio
async def test_throttle_serializes_concurrent_request_starts(monkeypatch):
    clock = [0.0]
    waits = []

    async def sleep(delay):
        waits.append(delay)
        clock[0] += delay

    monkeypatch.setattr("app.providers.base.time.monotonic", lambda: clock[0])
    monkeypatch.setattr("app.providers.base.asyncio.sleep", sleep)
    limiter = RateLimiter(0.2)
    await asyncio.gather(*(limiter.acquire() for _ in range(4)))
    assert waits == pytest.approx([0.2, 0.2, 0.2])


@pytest.mark.asyncio
async def test_sec_throttle_cannot_exceed_ten_requests_per_second():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))) as client:
        assert SecEdgarProvider(client, CONTACT, min_interval=0).limiter.min_interval == 0.1


@pytest.mark.asyncio
async def test_disabled_market_provider_cannot_invent_quotes():
    provider = DisabledMarketDataProvider()
    assert not provider.enabled
    for method in (provider.quote, provider.profile, provider.historical_prices, provider.dividends):
        with pytest.raises(ProviderError) as captured:
            await method("MSFT")
        assert captured.value.code == "provider_disabled"


@pytest.mark.asyncio
async def test_market_quote_profile_currency_timestamp_and_history(no_wait):
    requests = []
    instant = datetime.now(UTC).replace(microsecond=0)

    def handler(request):
        requests.append(request)
        assert request.url.host == "financialmodelingprep.com"
        assert request.url.params["apikey"] == "offline-fixture-key"
        if request.url.path == "/stable/quote":
            return httpx.Response(200, json=[{"symbol": "MSFT", "price": 100.25, "marketCap": 1002500, "sharesOutstanding": 10000, "timestamp": int(instant.timestamp())}])
        if request.url.path == "/stable/profile":
            return httpx.Response(200, json=[{"symbol": "MSFT", "companyName": "Fixture Company", "currency": "USD", "exchange": "NASDAQ"}])
        if request.url.path == "/stable/historical-price-eod/full":
            return httpx.Response(200, json=[{"symbol": "MSFT", "date": "2024-12-30", "close": 99}, {"symbol": "MSFT", "date": "2024-12-31", "close": 100}])
        return httpx.Response(200, json=[{"symbol": "MSFT", "date": "2024-12-01", "dividend": 0.5, "adjDividend": 0.5}])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = FmpMarketDataProvider(client, "offline-fixture-key")
        quote = await provider.quote("MSFT")
        assert quote["price"] == 100.25
        assert quote["currency"] == "USD"
        assert datetime.fromisoformat(quote["price_timestamp"]) == instant
        assert quote["shares_outstanding"] == 10000
        assert quote["warnings"] == []
        assert (await provider.historical_prices("MSFT", 1))[0]["date"] == "2024-12-31"
        assert (await provider.dividends("MSFT"))[0]["dividend"] == 0.5
    assert sum(request.url.path == "/stable/profile" for request in requests) == 1


@pytest.mark.asyncio
async def test_market_staleness_currency_and_missing_price_timestamp(no_wait):
    old = int((datetime.now(UTC) - timedelta(days=10)).timestamp())

    def handler(request):
        return httpx.Response(200, json=[{"symbol": "MSFT", "price": 100, "currency": "EUR", "exchange": "TEST", "timestamp": old}])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        quote = await FmpMarketDataProvider(client, "offline-fixture-key").quote("MSFT")
    assert {item["code"] for item in quote["warnings"]} >= {"stale_market_price", "incompatible_currency"}


@pytest.mark.asyncio
async def test_market_missing_timestamp_and_zero_price(no_wait):
    price = [100]

    def handler(request):
        return httpx.Response(200, json=[{"symbol": "MSFT", "price": price[0], "currency": "USD", "exchange": "NASDAQ"}])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = FmpMarketDataProvider(client, "offline-fixture-key")
        quote = await provider.quote("MSFT")
        assert quote["price_timestamp"] is None
        assert any(warning["code"] == "missing_price_timestamp" for warning in quote["warnings"])
        price[0] = 0
        with pytest.raises(ProviderError) as captured:
            await provider.quote("MSFT")
        assert captured.value.code == "invalid_provider_response"


@pytest.mark.asyncio
async def test_market_share_class_uses_sec_canonical_hyphen_spelling():
    def handler(request):
        assert request.url.params["symbol"] == "BRK-B"
        return httpx.Response(200, json=[{"symbol": "BRK-B", "price": 300, "currency": "USD", "exchange": "NYSE", "timestamp": int(datetime.now(UTC).timestamp())}])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        quote = await FmpMarketDataProvider(client, "offline-fixture-key").quote("BRK.B")
    assert quote["ticker"] == "BRK-B"


@pytest.mark.asyncio
async def test_market_invalid_share_count_and_inconsistent_cap_are_warned(no_wait):
    shares = [10]

    def handler(request):
        return httpx.Response(200, json=[{"symbol": "MSFT", "price": 100, "currency": "USD", "exchange": "NASDAQ", "timestamp": int(datetime.now(UTC).timestamp()), "marketCap": 10000, "sharesOutstanding": shares[0]}])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = FmpMarketDataProvider(client, "offline-fixture-key")
        quote = await provider.quote("MSFT")
        assert quote["market_cap"] == 10000
        assert any(item["code"] == "inconsistent_market_cap" for item in quote["warnings"])
        shares[0] = -1
        quote = await provider.quote("MSFT")
        assert quote["shares_outstanding"] is None
        assert any(item["code"] == "invalid_share_count" for item in quote["warnings"])


@pytest.mark.asyncio
async def test_market_bool_price_is_rejected():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[{"symbol": "MSFT", "price": True}]))) as client:
        with pytest.raises(ProviderError) as captured:
            await FmpMarketDataProvider(client, "offline-fixture-key").quote("MSFT")
    assert captured.value.code == "invalid_provider_response"


@pytest.mark.asyncio
async def test_fmp_error_json_is_safe_and_missing_api_key_disables_access():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"Error Message": "API key offline-secret does not have access"}))) as client:
        with pytest.raises(ProviderError) as captured:
            await FmpMarketDataProvider(client, "offline-fixture-key").quote("MSFT")
        assert captured.value.code == "provider_access_denied"
        assert "offline-secret" not in captured.value.message
        with pytest.raises(ProviderError) as disabled:
            await FmpMarketDataProvider(client, "").quote("MSFT")
        assert disabled.value.code == "provider_disabled"


@pytest.mark.asyncio
async def test_subscription_restrictions_are_not_retried_and_are_symbol_specific():
    requests = []
    def handler(request):
        requests.append(request.url.params['symbol'])
        if request.url.params['symbol'] == 'ORCL':
            return httpx.Response(402, text='Subscription error with private upstream detail')
        return httpx.Response(200, json=[{'symbol':'AAPL','price':100,'currency':'USD','exchange':'NASDAQ','timestamp':int(datetime.now(UTC).timestamp())}])
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = FmpMarketDataProvider(client, 'offline-fixture-key', retries=2)
        for _ in range(3):
            with pytest.raises(ProviderError) as denied:
                await provider.quote('ORCL')
            assert denied.value.code == 'provider_subscription_required'
            assert denied.value.retryable is False
            assert 'private' not in denied.value.message
        assert (await provider.quote('AAPL'))['price'] == 100
    assert requests == ['ORCL','AAPL']


@pytest.mark.asyncio
async def test_history_and_dividends_survive_unavailable_optional_profile():
    calls = []
    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith('/profile'):
            return httpx.Response(403)
        if request.url.path.endswith('/dividends'):
            return httpx.Response(200, json=[{'symbol':'AAPL','date':'2025-01-01','dividend':0.5}])
        return httpx.Response(200, json=[{'symbol':'AAPL','date':'2025-01-01','close':100}])
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = FmpMarketDataProvider(client, 'offline-fixture-key')
        prices = await provider.historical_prices('AAPL')
        dividends = await provider.dividends('AAPL')
        assert prices[0]['close'] == 100 and prices[0]['currency'] is None
        assert dividends[0]['dividend'] == 0.5 and dividends[0]['currency'] is None
    assert calls.count('/stable/profile') == 1
