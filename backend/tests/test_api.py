from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.core.database import utcnow
from app.main import create_app
from app.models import CacheEntry, FinancialFact
from app.providers.market_data import DisabledMarketDataProvider


@pytest.fixture
def client(engine, fake_providers):
    application = create_app(Settings(_env_file=None, database_url="sqlite://"), engine=engine, providers=fake_providers)
    with TestClient(application) as test_client:
        yield test_client


def test_health_search_company_and_openapi(client):
    assert client.get("/api/health").json()["database"] == "ready"
    search = client.get("/api/stocks/search", params={"q": "MSFT", "limit": 1})
    assert search.status_code == 200
    assert search.json()["results"][0]["cik"] == "0000000001"
    profile = client.get("/api/stocks/msft")
    assert profile.status_code == 200
    body = profile.json()
    assert body["company"]["ticker"] == "MSFT"
    assert body["market"]["price"] == 100
    assert body["market"]["price_timestamp"].endswith(("Z", "+00:00"))
    assert body["market"]["provider"] == "fixture-market"
    assert body["source_references"][0]["url"].endswith("CIK0000000001.json")
    spec = client.get("/openapi.json").json()
    assert spec["paths"]["/api/stocks/{ticker}/financials"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("FinancialResponse")


def test_financials_metrics_status_and_provenance(client, session_factory, fake_providers):
    financials = client.get("/api/stocks/MSFT/financials?period=annual&limit=1")
    assert financials.status_code == 200
    body = financials.json()
    latest = body["periods"][0]
    assert latest["fiscal_year"] == 2024
    assert latest["start_date"] == "2024-01-01"
    assert latest["metrics"]["revenue"] == 1000
    assert latest["metrics"]["free_cash_flow"] == 100
    assert latest["provenance"]["revenue"][0]["accn"] == "0000000001-25-000001"
    metrics = client.get("/api/stocks/MSFT/metrics").json()
    assert metrics["periods"][0]["metrics"]["net_profit_margin"] == pytest.approx(0.1)
    status = client.get("/api/stocks/MSFT/data-status").json()
    assert status["last_financial_update"]
    assert status["last_market_update"]
    assert status["available_periods"]["annual"][0]["fiscal_year"] == 2024
    assert status["provider_status"]["financial"]["provider"] == "sec-edgar"
    with session_factory() as session:
        assert session.scalar(select(FinancialFact).where(FinancialFact.normalized_metric == "revenue")) is not None
    assert fake_providers[0].facts_calls == 1
    quarterly = client.get("/api/stocks/MSFT/financials?period=quarterly").json()
    assert quarterly["periods"] == []
    assert any(issue["code"] == "no_reporting_periods" for issue in quarterly["warnings"])


def test_historical_prices_are_bounded_and_timestamped(client):
    response = client.get("/api/stocks/MSFT/prices?limit=1")
    assert response.status_code == 200
    assert response.json()["prices"] == [{"date": "2024-12-31", "close": 100, "open": None, "high": None, "low": None, "volume": 1000, "adjusted_close": None}]
    assert response.json()["retrieved_at"]
    assert response.json()["provider"] == "fixture-market"


@pytest.mark.parametrize("path", ["/api/stocks/search?q=x&limit=51", "/api/stocks/search?q=", "/api/stocks/123BAD",
                                       "/api/stocks/MSFT/financials?period=monthly", "/api/stocks/MSFT/prices?limit=-1", "/api/stocks/ABCDEFGHIJK"])
def test_invalid_inputs_return_structured_errors(client, path):
    response = client.get(path)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    assert "traceback" not in response.text.lower()


def test_unsupported_ticker_and_uncached_provider_failure(client, fake_providers):
    unsupported = client.get("/api/stocks/ZZZZ")
    assert unsupported.status_code == 404
    assert unsupported.json()["error"]["code"] == "unsupported_ticker"
    fake_providers[0].fail_company = True
    failed = client.get("/api/stocks/AAPL")
    assert failed.status_code == 503
    assert failed.json()["error"]["code"] == "provider_timeout"


def test_financial_provider_failure_returns_explicit_stale_cache(client, fake_providers, session_factory):
    first = client.get("/api/stocks/MSFT/financials").json()
    with session_factory.begin() as session:
        for key in ("sec:financials:0000000001:MSFT", "sec:facts:0000000001"):
            session.get(CacheEntry, key).expires_at = utcnow() - timedelta(seconds=1)
    fake_providers[0].fail_facts = True
    response = client.get("/api/stocks/MSFT/financials")
    assert response.status_code == 200
    assert response.json()["status"] == "stale"
    assert response.json()["periods"] == first["periods"]
    assert any(issue["code"] == "stale_provider_failure" for issue in response.json()["warnings"])


def test_market_provider_disabled_retains_real_sec_profile_without_fake_price(engine, raw_facts):
    from conftest import FakeSec
    application = create_app(Settings(_env_file=None), engine=engine, providers=(FakeSec(raw_facts), DisabledMarketDataProvider()))
    with TestClient(application) as client:
        response = client.get("/api/stocks/MSFT")
        assert response.status_code == 200
        assert response.json()["market"] is None
        assert response.json()["status"] == "partial"
        assert response.json()["company"]["name"] == "Fixture Company"
        assert any(issue["code"] == "provider_disabled" for issue in response.json()["warnings"])
        assert client.get("/api/stocks/MSFT/prices").status_code == 503


def test_currency_mismatch_and_stale_market_timestamp_are_visible(client, fake_providers):
    fake_providers[1].currency = "EUR"
    fake_providers[1].timestamp = "2020-01-01T20:00:00Z"
    response = client.get("/api/stocks/MSFT").json()
    assert response["market"]["price"] == 100
    assert response["market"]["status"] == "stale"
    assert {issue["code"] for issue in response["warnings"]} >= {"incompatible_currencies", "stale_market_price"}


def test_config_rejects_wildcard_cors_and_unrecognized_provider():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Settings(_env_file=None, cors_origins=["*"])
    with pytest.raises(ValidationError):
        Settings(_env_file=None, market_data_provider="arbitrary-url")


def test_health_is_unavailable_before_migrations(tmp_path, fake_providers):
    from sqlalchemy import create_engine
    engine = create_engine(f"sqlite:///{tmp_path / 'unmigrated.sqlite'}", connect_args={"check_same_thread": False})
    application = create_app(Settings(_env_file=None), engine=engine, providers=fake_providers)
    with TestClient(application) as client:
        response = client.get("/api/health")
        assert response.status_code == 503
        assert response.json()["database"] == "unavailable"


def test_canonical_share_class_alias_is_used_for_market_requests(client, fake_providers):
    sec, market = fake_providers
    seen = []
    original_company = sec.company
    original_quote = market.quote
    original_profile = market.profile

    async def canonical(_ticker):
        return {**await original_company("MSFT"), "ticker": "BRK-B"}

    async def quote(ticker):
        seen.append(ticker)
        return await original_quote(ticker)

    async def profile(ticker):
        seen.append(ticker)
        return await original_profile(ticker)

    sec.company, market.quote, market.profile = canonical, quote, profile
    assert client.get("/api/stocks/BRK.B").json()["company"]["ticker"] == "BRK-B"
    assert seen == ["BRK-B", "BRK-B"]


def test_shared_cik_persists_both_share_classes_with_one_sec_fetch(client, fake_providers, session_factory):
    from sqlalchemy import func
    from app.models import Company, FinancialSnapshot
    sec, _ = fake_providers
    original_company = sec.company

    async def share_class(ticker):
        return {**await original_company("MSFT"), "ticker": ticker, "has_multiple_share_classes": True,
                "share_class_basis_verified": False,
                "warnings": [{"field": "shares", "code": "share_class_basis_unverified", "message": "Fixture share class warning."}]}

    sec.company = share_class
    for ticker in ("GOOG", "GOOGL"):
        response = client.get(f"/api/stocks/{ticker}/financials")
        assert response.status_code == 200
        assert response.json()["periods"][0]["metrics"]["revenue"] == 1000
    assert sec.facts_calls == 1
    with session_factory() as session:
        for ticker in ("GOOG", "GOOGL"):
            company = session.scalar(select(Company).where(Company.ticker == ticker))
            assert session.scalar(select(func.count()).select_from(FinancialFact).where(FinancialFact.company_id == company.id)) > 0
            assert session.scalar(select(func.count()).select_from(FinancialSnapshot).where(FinancialSnapshot.company_id == company.id)) == 1
    profile = client.get("/api/stocks/GOOGL").json()
    assert profile["company"]["has_multiple_share_classes"] is True
    assert profile["company"]["share_class_basis_verified"] is False
    assert profile["status"] == "partial"
    assert sum(issue["code"] == "share_class_basis_unverified" for issue in profile["warnings"]) == 1
    assert any(issue["code"] == "share_class_basis_unverified" for issue in client.get("/api/stocks/GOOGL/data-status").json()["warnings"])


def test_new_share_class_uses_stale_shared_facts_without_refreshing_timestamp(client, fake_providers, session_factory):
    sec, _ = fake_providers
    original_company = sec.company

    async def share_class(ticker):
        return {**await original_company("MSFT"), "ticker": ticker, "has_multiple_share_classes": True}

    sec.company = share_class
    original = client.get("/api/stocks/GOOG/financials").json()
    with session_factory.begin() as session:
        session.get(CacheEntry, "sec:facts:0000000001").expires_at = utcnow() - timedelta(seconds=1)
    sec.fail_facts = True
    stale = client.get("/api/stocks/GOOGL/financials").json()
    assert stale["status"] == "stale"
    assert stale["retrieved_at"] == original["retrieved_at"]
    with session_factory() as session:
        assert session.get(CacheEntry, "sec:financials:0000000001:GOOGL") is None


def test_historical_prices_expose_stale_identity_metadata(client, fake_providers, session_factory):
    assert client.get("/api/stocks/MSFT/prices").status_code == 200
    with session_factory.begin() as session:
        session.get(CacheEntry, "sec:company:MSFT").expires_at = utcnow() - timedelta(seconds=1)
    fake_providers[0].fail_company = True
    response = client.get("/api/stocks/MSFT/prices").json()
    assert response["status"] == "stale"
    assert any(issue["code"] == "stale_provider_failure" for issue in response["warnings"])
