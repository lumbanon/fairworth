"""Optional, credentialed FMP stable API adapter.

Access and redistribution depend on the configured subscription and licenses.
No market price is inferred from financial statements or demo data.
https://site.financialmodelingprep.com/developer/docs/quickstart
"""

from __future__ import annotations

import math
import asyncio
import time
from copy import deepcopy
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import httpx

from app.providers.base import JsonHttpProvider, ProviderError, validate_ticker
from app.services.security_identity import cache_scope, check_provider_identity
from app.providers.capabilities import capability_record, capability_snapshot
from app.providers.currency import make_currency_evidence, resolve_quote_currency


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
    supports_security_identity = True
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
        access_denial_ttl_seconds: int = 3600,
    ) -> None:
        # FMP's free allowance must not be consumed by automatic retries or
        # repeated entitlement probes. SEC transport policy is independent.
        super().__init__(client, min_interval=min_interval, retries=0, timeout=timeout)
        self.api_key = api_key.strip()
        self.enabled = bool(self.api_key)
        self.stale_price_seconds = max(60, stale_price_seconds)
        self.access_denial_ttl_seconds = max(60, access_denial_ttl_seconds)
        self._profiles: dict[str, tuple[float, dict]] = {}
        self._access_denials = {}
        self._endpoint_locks = {}
        self._endpoint_users = {}
        self._capabilities = {}

    def capability(self, endpoint, ticker, identity=None):
        symbol = self._symbol(ticker, identity)
        key = (endpoint, cache_scope(identity) if identity else symbol)
        return deepcopy(self._capabilities.get(key, capability_record(endpoint)))

    def capability_snapshot(self, ticker, identity=None):
        from app.providers.capabilities import ENDPOINTS
        scope = identity or {"ticker": self._symbol(ticker, identity)}
        return capability_snapshot({endpoint: self.capability(endpoint, ticker, identity) for endpoint in ENDPOINTS}, scope)

    def _observe_capability(self, key, error=None):
        self._remember(self._capabilities, key, capability_record(key[0], observed_at=datetime.now(UTC).isoformat(),
                       error_code=error.code if error else None, success=error is None))

    def _cached_profile(self, ticker, identity=None):
        key = cache_scope(identity) if identity else self._symbol(ticker, identity)
        cached = self._profiles.get(key)
        return deepcopy(cached[1]) if cached is not None and time.monotonic() - cached[0] < 3600 else {}

    @staticmethod
    def _remember(mapping, key, value):
        mapping.pop(key, None)
        mapping[key] = value
        while len(mapping) > 1000:
            mapping.pop(next(iter(mapping)))

    @asynccontextmanager
    async def _endpoint_lock(self, key):
        lock = self._endpoint_locks.setdefault(key, asyncio.Lock())
        self._endpoint_users[key] = self._endpoint_users.get(key, 0) + 1
        try:
            async with lock:
                yield
        finally:
            self._endpoint_users[key] -= 1
            if not self._endpoint_users[key]:
                self._endpoint_users.pop(key)
                self._endpoint_locks.pop(key)

    async def _records(self, endpoint: str, ticker: str, parameters: dict | None = None, identity: dict | None = None) -> list[dict]:
        if not self.enabled:
            raise ProviderError("provider_disabled", "The market provider API key is not configured.", 503)
        symbol = self._symbol(ticker, identity)
        key = (endpoint, cache_scope(identity) if identity else symbol)
        # Access can differ by symbol. Do not let an ORCL restriction disable AAPL.
        async with self._endpoint_lock(key):
            denial = self._access_denials.get(key)
            permanent = denial and denial[1] in {"provider_subscription_required", "provider_access_denied", "provider_authentication_failed"}
            if denial and (permanent or time.monotonic() - denial[0] < self.access_denial_ttl_seconds):
                raise ProviderError(denial[1], denial[2], 503)
            try:
                # endpoint is an internal constant; no user-controlled URL is accepted.
                payload = await self._json(
                    f"{self.ORIGIN}/{endpoint}", params={**(parameters or {}), "symbol": symbol, "apikey": self.api_key}
                )
                if isinstance(payload, dict) and any(key in payload for key in ("Error Message", "error", "Error")):
                    raise ProviderError(
                        "provider_access_denied", "The market provider could not fulfill this request. Check access permissions.", 503
                    )
            except ProviderError as error:
                self._observe_capability(key, error)
                if error.code in {"provider_subscription_required", "provider_access_denied", "provider_authentication_failed", "provider_rate_limited"}:
                    self._remember(self._access_denials, key, (time.monotonic(), error.code, error.message))
                raise
            self._access_denials.pop(key, None)
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise ProviderError("invalid_provider_response", "The market provider returned an unexpected response.", 502)
        if identity:
            for row in payload:
                check_provider_identity(identity, row)
        self._observe_capability(key)
        return payload

    @staticmethod
    def _symbol(ticker, identity):
        symbols = (identity or {}).get("provider_symbols") or {}
        alias = symbols.get("fmp") if isinstance(symbols, dict) else None
        if identity:
            return validate_ticker(alias if isinstance(alias, str) else identity.get("ticker", ticker))
        return _market_symbol(ticker)

    async def profile(self, ticker: str, identity: dict | None = None) -> dict:
        symbol = self._symbol(ticker, identity)
        profile_key = cache_scope(identity) if identity else symbol
        cached = self._profiles.get(profile_key)
        if cached is not None and time.monotonic() - cached[0] < 3600:
            return dict(cached[1])
        rows = await self._records("profile", symbol, identity=identity)
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
            "beta": _number(row.get("beta")),
            "beta_methodology": "FMP current profile beta; provider lookback and return frequency are not supplied in this endpoint.",
            "ipo_date": row.get("ipoDate") or None,
            "retrieved_at": datetime.now(UTC).isoformat(),
            "provider": self.name,
        }
        result["currency_evidence"] = make_currency_evidence(row, identity, source_kind="provider_security_metadata", retrieved_at=result["retrieved_at"])
        if identity:
            check_provider_identity(identity, result)
        self._remember(self._profiles, profile_key, (time.monotonic(), result))
        return dict(result)

    async def quote(self, ticker: str, identity: dict | None = None) -> dict:
        symbol = self._symbol(ticker, identity)
        rows = await self._records("quote", symbol, identity=identity)
        row = next((item for item in rows if item.get("symbol") == symbol), None)
        if row is None:
            raise ProviderError("not_found", "The market provider has no quote for this ticker.", 404)
        price = _number(row.get("price"))
        if price is None or price <= 0:
            raise ProviderError("invalid_provider_response", "The market provider returned an invalid stock price.", 502)
        warnings = []
        profile = self._cached_profile(symbol, identity)
        if (not row.get("currency") or not row.get("exchange")) and not profile:
            warnings.append({"field": "currency", "code": "missing_quote_metadata", "message": "Quote currency or exchange metadata is unavailable; no additional provider endpoint was requested."})
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
        currency = row.get("currency") or None
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
        result = {
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
        result["currency_evidence"] = make_currency_evidence(row, identity, source_kind="provider_quote", retrieved_at=result["retrieved_at"])
        result = resolve_quote_currency(result, identity, [profile["currency_evidence"]] if profile.get("currency_evidence") else [])
        warnings = result["warnings"]
        if result["currency_resolution"]["status"] != "verified":
            warnings.append({"field": "currency", "code": "quote_currency_unverified" if result["currency_resolution"]["status"] != "conflict" else "conflicting_quote_currency",
                "message": "The observed quote has no compatible source-backed currency; currency-sensitive results remain unavailable."})
        elif result["currency"] != "USD":
            warnings.append({"field": "currency", "code": "incompatible_currency", "message": "The quote currency is not USD and cannot be combined with USD financial statements without a sourced conversion."})
        result["provider_capability"] = self.capability("quote", symbol, identity)
        result["provider_capabilities"] = self.capability_snapshot(symbol, identity)
        return result

    async def historical_prices(self, ticker: str, limit: int = 365, identity: dict | None = None) -> list[dict]:
        symbol = self._symbol(ticker, identity)
        rows = await self._records("historical-price-eod/full", symbol, identity=identity)
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
                "currency": row.get("currency"),
                "provider": self.name,
                # FMP documents full EOD as split adjusted. It is distinct from
                # its dividend-adjusted endpoint, which is unsuitable for P/E.
                "adjustment_basis": "split_adjusted",
                "adjustment_date": datetime.now(UTC).date().isoformat(),
            })
        result.sort(key=lambda item: item["date"], reverse=True)
        return result[: min(2000, max(1, limit))]

    async def dividends(self, ticker: str, limit: int = 100, identity: dict | None = None) -> list[dict]:
        symbol = self._symbol(ticker, identity)
        rows = await self._records("dividends", symbol, identity=identity)
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
                "currency": row.get("currency"),
                "provider": self.name,
            })
        return result[: min(1000, max(1, limit))]

    async def splits(self, ticker: str, identity: dict | None = None) -> list[dict]:
        """Full authorized split-event endpoint; a denied call is not no splits."""
        symbol = self._symbol(ticker, identity)
        rows = await self._records("splits", symbol, {"limit": 1000}, identity=identity)
        result = []
        for row in rows:
            if row.get("symbol", symbol) != symbol:
                continue
            numerator, denominator = _number(row.get("numerator")), _number(row.get("denominator"))
            try:
                day = datetime.strptime(str(row.get("date")), "%Y-%m-%d").date().isoformat()
            except ValueError:
                raise ProviderError("invalid_provider_response", "A split observation has an invalid date.", 502) from None
            if numerator is None or denominator is None or numerator <= 0 or denominator <= 0:
                raise ProviderError("invalid_provider_response", "A split observation has an invalid ratio.", 502)
            result.append({"date": day, "numerator": numerator, "denominator": denominator, "provider": self.name})
        return sorted(result, key=lambda item: item["date"])

    async def share_float(self, ticker: str, identity: dict | None = None) -> dict:
        symbol = self._symbol(ticker, identity)
        rows = await self._records("shares-float", symbol, identity=identity)
        row = next((item for item in rows if item.get("symbol") == symbol), None)
        if row is None:
            raise ProviderError("not_found", "The provider has no share-float observation for this ticker.", 404)
        shares = _number(row.get("outstandingShares"))
        if shares is None or shares <= 0:
            raise ProviderError("invalid_provider_response", "The share-float endpoint did not supply a valid outstanding share count.", 502)
        return {"ticker": symbol, "shares_outstanding": shares, "date": row.get("date"),
                "source_url": row.get("source"), "provider": self.name,
                "retrieved_at": datetime.now(UTC).isoformat()}

    async def financial_statements(self, ticker: str, kind: str, limit: int = 6, identity: dict | None = None) -> list[dict]:
        endpoints = {"balance_sheet": "balance-sheet-statement", "cash_flow": "cash-flow-statement"}
        if kind not in endpoints:
            raise ProviderError("unsupported_statement", "This supplemental statement type is unsupported.", 400)
        return await self._records(endpoints[kind], ticker, {"period": "annual", "limit": min(10, max(1, limit))}, identity=identity)
