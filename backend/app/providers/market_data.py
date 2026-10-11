"""Optional, credentialed FMP stable API adapter.

Access and redistribution depend on the configured subscription and licenses.
No market price is inferred from financial statements or demo data.
https://site.financialmodelingprep.com/developer/docs/quickstart
"""

from __future__ import annotations

import math
import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

import httpx

from app.providers.base import JsonHttpProvider, ProviderError, validate_ticker


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _market_symbol(ticker: str) -> str:
    # Match the SEC directory's US share-class spelling (BRK.B -> BRK-B).
    return validate_ticker(ticker).replace(".", "-")


class MarketDataProvider(ABC):
    name = "disabled"
    enabled = False

    @abstractmethod
    async def quote(self, ticker: str) -> dict: ...

    @abstractmethod
    async def profile(self, ticker: str) -> dict: ...

    @abstractmethod
    async def historical_prices(self, ticker: str, limit: int = 365) -> list[dict]: ...

    @abstractmethod
    async def dividends(self, ticker: str, limit: int = 100) -> list[dict]: ...


class DisabledMarketDataProvider(MarketDataProvider):
    """Explicit absence of market data, never an invented or demo quote."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self.client = client

    @staticmethod
    def _unavailable(ticker: str) -> None:
        validate_ticker(ticker)
        raise ProviderError(
            "provider_disabled", "A licensed market data provider has not been configured.", 503
        )

    async def quote(self, ticker: str) -> dict:
        self._unavailable(ticker)

    async def profile(self, ticker: str) -> dict:
        self._unavailable(ticker)

    async def historical_prices(self, ticker: str, limit: int = 365) -> list[dict]:
        self._unavailable(ticker)

    async def dividends(self, ticker: str, limit: int = 100) -> list[dict]:
        self._unavailable(ticker)


class FmpMarketDataProvider(JsonHttpProvider, MarketDataProvider):
    name = "fmp"
    ORIGIN = "https://financialmodelingprep.com/stable"

    def __init__(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        min_interval: float = 0.2,
        retries: int = 2,
        timeout: float = 20,
        stale_price_seconds: int = 259200,
    ) -> None:
        super().__init__(client, min_interval=min_interval, retries=retries, timeout=timeout)
        self.api_key = api_key.strip()
        self.enabled = bool(self.api_key)
        self.stale_price_seconds = max(60, stale_price_seconds)
        self._profiles: dict[str, tuple[float, dict]] = {}

    async def _records(self, endpoint: str, ticker: str) -> list[dict]:
        if not self.enabled:
            raise ProviderError("provider_disabled", "The market provider API key is not configured.", 503)
        symbol = _market_symbol(ticker)
        # endpoint is an internal constant; no user-controlled URL is accepted.
        payload = await self._json(
            f"{self.ORIGIN}/{endpoint}", params={"symbol": symbol, "apikey": self.api_key}
        )
        if isinstance(payload, dict) and ("Error Message" in payload or "error" in payload):
            raise ProviderError(
                "provider_access_denied", "The market provider could not fulfill this request. Check access permissions.", 503
            )
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise ProviderError("invalid_provider_response", "The market provider returned an unexpected response.", 502)
        return payload

    async def profile(self, ticker: str) -> dict:
        symbol = _market_symbol(ticker)
        cached = self._profiles.get(symbol)
        if cached is not None and time.monotonic() - cached[0] < 3600:
            return dict(cached[1])
        rows = await self._records("profile", symbol)
        row = next((item for item in rows if item.get("symbol") == symbol), None)
        if row is None:
            raise ProviderError("not_found", "The market provider has no company profile for this ticker.", 404)
        result = {
            "ticker": symbol,
            "name": row.get("companyName") or None,
            "exchange": row.get("exchange") or row.get("exchangeFullName") or None,
            "currency": row.get("currency") or None,
            "sector": row.get("sector") or None,
            "industry": row.get("industry") or None,
            "description": row.get("description") or None,
            "cik": row.get("cik") or None,
            "provider": self.name,
        }
        self._profiles[symbol] = (time.monotonic(), result)
        return dict(result)

    async def quote(self, ticker: str) -> dict:
        symbol = _market_symbol(ticker)
        rows = await self._records("quote", symbol)
        row = next((item for item in rows if item.get("symbol") == symbol), None)
        if row is None:
            raise ProviderError("not_found", "The market provider has no quote for this ticker.", 404)
        price = _number(row.get("price"))
        if price is None or price <= 0:
            raise ProviderError("invalid_provider_response", "The market provider returned an invalid stock price.", 502)
        warnings = []
        profile = {}
        if not row.get("currency") or not row.get("exchange"):
            try:
                profile = await self.profile(symbol)
            except ProviderError:
                warnings.append({"field": "currency", "code": "missing_quote_metadata", "message": "Quote currency or exchange metadata is unavailable."})
        timestamp = _number(row.get("timestamp"))
        price_timestamp = None
        if timestamp is not None:
            try:
                instant = datetime.fromtimestamp(timestamp, UTC)
                price_timestamp = instant.isoformat()
                age = (datetime.now(UTC) - instant).total_seconds()
                if age > self.stale_price_seconds:
                    warnings.append({"field": "price", "code": "stale_market_price", "message": "The latest available market quote is older than the configured freshness threshold."})
                elif age < -300:
                    warnings.append({"field": "price_timestamp", "code": "future_price_timestamp", "message": "The market quote timestamp is in the future."})
            except (ValueError, OSError, OverflowError):
                pass
        if price_timestamp is None:
            warnings.append({"field": "price_timestamp", "code": "missing_price_timestamp", "message": "The provider did not supply a usable market price timestamp."})
        currency = row.get("currency") or profile.get("currency") or None
        if currency is None:
            warnings.append({"field": "currency", "code": "missing_currency", "message": "The quote currency is unavailable; currency-sensitive calculations must remain unavailable."})
        if currency is not None and currency != "USD":
            warnings.append({"field": "currency", "code": "incompatible_currency", "message": "The quote currency is not USD and cannot be combined with USD financial statements without a sourced conversion."})
        market_cap = _number(row.get("marketCap"))
        shares = _number(row.get("sharesOutstanding"))
        if market_cap is not None and market_cap <= 0:
            market_cap = None
            warnings.append({"field": "market_cap", "code": "invalid_market_cap", "message": "A nonpositive provider market capitalization was excluded."})
        if shares is not None and shares <= 0:
            shares = None
            warnings.append({"field": "shares_outstanding", "code": "invalid_share_count", "message": "A nonpositive provider share count was excluded."})
        if market_cap is not None and shares is not None and abs(market_cap - price * shares) > market_cap * 0.1:
            warnings.append({"field": "market_cap", "code": "inconsistent_market_cap", "message": "Market capitalization differs from the supplied price/share-count basis by more than 10%; reported values were not recalculated."})
        return {
            "ticker": symbol,
            "price": price,
            "currency": currency,
            "exchange": row.get("exchange") or profile.get("exchange") or None,
            "price_timestamp": price_timestamp,
            "market_cap": market_cap,
            "shares_outstanding": shares,
            "provider": self.name,
            "retrieved_at": datetime.now(UTC).isoformat(),
            "warnings": warnings,
        }

    async def historical_prices(self, ticker: str, limit: int = 365) -> list[dict]:
        symbol = _market_symbol(ticker)
        rows = await self._records("historical-price-eod/full", symbol)
        profile = await self.profile(symbol)
        result = []
        for row in rows:
            if row.get("symbol", symbol) != symbol:
                continue
            close = _number(row.get("close"))
            try:
                day = datetime.strptime(str(row.get("date")), "%Y-%m-%d").date().isoformat()
            except ValueError:
                continue
            if close is None or close <= 0:
                continue
            result.append({
                "date": day,
                "close": close,
                "open": _number(row.get("open")),
                "high": _number(row.get("high")),
                "low": _number(row.get("low")),
                "volume": _number(row.get("volume")),
                "currency": profile.get("currency"),
                "provider": self.name,
            })
        result.sort(key=lambda item: item["date"], reverse=True)
        return result[: min(2000, max(1, limit))]

    async def dividends(self, ticker: str, limit: int = 100) -> list[dict]:
        symbol = _market_symbol(ticker)
        rows = await self._records("dividends", symbol)
        profile = await self.profile(symbol)
        result = []
        for row in rows:
            amount = _number(row.get("dividend"))
            if row.get("symbol", symbol) != symbol or amount is None or amount < 0:
                continue
            result.append({
                "date": row.get("date"),
                "dividend": amount,
                "adjusted_dividend": _number(row.get("adjDividend")),
                "declaration_date": row.get("declarationDate"),
                "record_date": row.get("recordDate"),
                "payment_date": row.get("paymentDate"),
                "currency": profile.get("currency"),
                "provider": self.name,
            })
        return result[: min(1000, max(1, limit))]
