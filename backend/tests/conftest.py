from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest
import httpx
from sqlalchemy import create_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import Base, build_session_factory
import app.models  # noqa: F401
from app.providers.base import ProviderError


@pytest.fixture(autouse=True)
def block_real_provider_http(monkeypatch):
    """Routine tests must use MockTransport/ASGI; never export configured keys.

    This blocks concrete HTTP transports while allowing dedicated PostgreSQL
    socket connections and local in-process API clients.
    """
    def blocked(*_args, **_kwargs):
        pytest.fail("Real HTTP is forbidden in the deterministic test suite.")

    async def async_blocked(*_args, **_kwargs):
        blocked()

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", async_blocked)


@pytest.fixture
def engine(tmp_path):
    database = create_engine(f"sqlite:///{tmp_path / 'test.sqlite'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(database)  # Test-only; production uses Alembic.
    yield database
    database.dispose()


@pytest.fixture
def session_factory(engine):
    return build_session_factory(engine)


@pytest.fixture
def raw_facts():
    concepts = {
        "RevenueFromContractWithCustomerExcludingAssessedTax": ("USD", 1000, False),
        "NetIncomeLoss": ("USD", 100, False), "Assets": ("USD", 1500, True),
        "Liabilities": ("USD", 600, True), "StockholdersEquity": ("USD", 900, True),
        "CashAndCashEquivalentsAtCarryingValue": ("USD", 200, True),
        "LongTermDebtCurrent": ("USD", 25, True), "LongTermDebtNoncurrent": ("USD", 125, True),
        "NetCashProvidedByUsedInOperatingActivities": ("USD", 150, False),
        "PaymentsToAcquirePropertyPlantAndEquipment": ("USD", 50, False),
        "WeightedAverageNumberOfDilutedSharesOutstanding": ("shares", 10, False),
        "EarningsPerShareDiluted": ("USD/shares", 10, False),
    }
    facts = {}
    for concept, (unit, value, instant) in concepts.items():
        observations = []
        for year, factor in ((2023, 0.8), (2024, 1)):
            item = {"val": value * factor, "end": f"{year}-12-31", "fy": year, "fp": "FY",
                    "form": "10-K", "filed": f"{year + 1}-02-15", "accn": f"0000000001-{str(year + 1)[2:]}-000001",
                    "frame": f"CY{year}" + ("Q4I" if instant else "")}
            if not instant:
                item["start"] = f"{year}-01-01"
            observations.append(item)
        facts[concept] = {"label": concept, "units": {unit: observations}}
    return {"cik": 1, "entityName": "Fixture Company", "facts": {"us-gaap": facts}}


class FakeSec:
    name = "sec"
    enabled = True

    def __init__(self, facts):
        self.raw_facts = facts
        self.fail_company = False
        self.fail_facts = False
        self.company_calls = 0
        self.facts_calls = 0

    async def search(self, q, limit=10):
        return [{"ticker": "MSFT", "name": "Fixture Company", "cik": "0000000001", "exchange": "NASDAQ"}][:limit]

    async def company(self, ticker):
        self.company_calls += 1
        if self.fail_company:
            raise ProviderError("provider_timeout", "The SEC provider timed out.", 503)
        if ticker not in {"MSFT", "AAPL"}:
            raise ProviderError("unsupported_ticker", "This ticker is not supported.", 404)
        return {"ticker": ticker, "name": "Fixture Company", "cik": "0000000001", "exchange": "NASDAQ",
                "sector": None, "industry": "Fixture Industry", "description": None, "currency": None, "sic": "3571"}

    async def facts(self, cik):
        self.facts_calls += 1
        if self.fail_facts:
            raise ProviderError("provider_timeout", "The SEC provider timed out.", 503)
        return self.raw_facts


class FakeMarket:
    name = "fixture-market"
    enabled = True

    def __init__(self):
        self.quote_calls = 0
        self.fail = False
        self.currency = "USD"
        self.timestamp = datetime.now(timezone.utc).isoformat()

    async def profile(self, ticker):
        if self.fail:
            raise ProviderError("provider_timeout", "The market provider timed out.", 503)
        return {"description": "Fixture company profile", "currency": self.currency}

    async def quote(self, ticker):
        self.quote_calls += 1
        if self.fail:
            raise ProviderError("provider_timeout", "The market provider timed out.", 503)
        return {"price": 100, "currency": self.currency, "exchange": "NASDAQ", "price_timestamp": self.timestamp,
                "market_cap": 1000, "shares_outstanding": 10, "provider": self.name, "warnings": []}

    async def historical_prices(self, ticker, limit=365):
        if self.fail:
            raise ProviderError("provider_timeout", "The market provider timed out.", 503)
        return [{"date": "2024-12-31", "close": 100, "volume": 1000}][:limit]


@pytest.fixture
def fake_providers(raw_facts):
    return FakeSec(raw_facts), FakeMarket()
