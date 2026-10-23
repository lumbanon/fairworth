"""Optional personal-use IBKR market data. No public service or database writes.

Construction never imports the SDK or connects. An explicit, bounded per-process
authorization is required even when local connection settings have been saved.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
import hashlib
import ipaddress
import json
import math
import re
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.providers.base import ProviderError, normalize_cik, validate_ticker
from app.providers.market_data import MarketDataProvider

PRIVATE = {"provider": "ibkr", "permitted_use": "personal_local_only", "public_redistribution_allowed": False}
DATA_TYPES = {1: "live", 2: "frozen", 3: "delayed", 4: "delayed_frozen"}
VENUES = {"XNAS": {"NASDAQ", "ISLAND"}, "XNYS": {"NYSE"}, "XASE": {"AMEX"}, "ARCX": {"ARCA"}}


def fail(code, message, status=422):
    raise ProviderError(code, message, status)


class IbkrConnection(BaseModel):
    """Only literal loopback addresses; no DNS, remote endpoints or passwords."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    host: str = "127.0.0.1"
    port: int | None = Field(default=None, ge=1, le=65535)
    client_id: int = Field(default=68, ge=1, le=2147483647)
    timeout_seconds: float = Field(default=15, ge=1, le=30)
    minimum_interval_seconds: float = Field(default=1, ge=1, le=60)

    @field_validator("host")
    @classmethod
    def loopback_only(cls, value):
        try:
            if not ipaddress.ip_address(value).is_loopback:
                raise ValueError()
        except ValueError:
            raise ValueError("IBKR host must be a literal loopback IP address.") from None
        return value


class IbkrAuthorization(BaseModel):
    """Operator supplies this only after approving the concrete connection plan."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    approval_reference: str = Field(min_length=1, max_length=100)
    symbols: tuple[str, ...] = Field(min_length=1, max_length=2)
    max_contract_lookups: int = Field(default=1, ge=1, le=2)
    max_quotes: int = Field(default=1, ge=0, le=2)
    max_history_requests: int = Field(default=0, ge=0, le=2)
    market_data_type: int = Field(default=1)
    personal_use_confirmed: bool = False
    api_non_display_use_confirmed: bool = False
    read_only_session_confirmed: bool = False
    local_retention_confirmed: bool = False

    @field_validator("symbols")
    @classmethod
    def exact_symbols(cls, values):
        normalized = tuple(validate_ticker(value) for value in values)
        if len(set(normalized)) != len(normalized):
            raise ValueError("IBKR authorization requires unique exact symbols.")
        return normalized

    @field_validator("market_data_type")
    @classmethod
    def explicit_type(cls, value):
        if value not in DATA_TYPES:
            raise ValueError("An explicit IBKR market-data type is required.")
        return value


class IbkrTransport(Protocol):
    simulated: bool
    async def connect(self, connection: IbkrConnection): ...
    async def close(self): ...
    async def contracts(self, request: dict) -> list[dict]: ...
    async def quote(self, contract: dict, market_data_type: int) -> dict: ...
    async def history(self, contract: dict, days: int) -> list[dict]: ...


def _number(value):
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0 else None


def _instant(value):
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result.astimezone(UTC) if result.tzinfo else None
    except (ValueError, TypeError):
        return None


class IbkrMarketDataProvider(MarketDataProvider):
    name = "ibkr"
    supports_security_identity = True
    permitted_use = "personal_local_only"

    def __init__(self, connection=None, *, transport=None, clock=None):
        self.connection = connection or IbkrConnection()
        self._transport = transport
        self._clock = clock or (lambda: datetime.now(UTC))
        self._authorization = None
        self._counts = {"contracts": 0, "quote": 0, "history": 0}
        self._contracts = {}
        self._last_start = None
        self._lock = asyncio.Lock()
        self.enabled = False

    async def open(self, authorization: IbkrAuthorization):
        if (not isinstance(authorization, IbkrAuthorization) or not authorization.personal_use_confirmed or not authorization.api_non_display_use_confirmed
                or not authorization.read_only_session_confirmed or self.connection.port is None):
            fail("ibkr_not_authorized", "An approved loopback connection plan and read-only personal-use session are required.", 403)
        if self._authorization is not None:
            fail("ibkr_request_budget_exhausted", "This provider instance cannot reconnect or reset its approved request budget.", 403)
        self._authorization = authorization
        if self._transport is None:
            from app.providers.ibkr_transport import OfficialIbkrTransport
            self._transport = OfficialIbkrTransport(timeout=self.connection.timeout_seconds)
        try:
            await asyncio.wait_for(self._transport.connect(self.connection), self.connection.timeout_seconds)
        except TimeoutError:
            await self._transport.close()
            fail("ibkr_timeout", "The approved IBKR connection timed out and was not retried.", 504)
        self.enabled = True
        return self

    async def close(self):
        self.enabled = False
        if self._transport:
            await self._transport.close()

    def _scope(self, ticker, identity):
        ticker = validate_ticker(ticker)
        if not self.enabled or self._authorization is None:
            fail("ibkr_not_authorized", "IBKR is disconnected; an explicitly approved local session is required.", 403)
        if ticker not in self._authorization.symbols:
            fail("ibkr_not_authorized", "This symbol is outside the approved IBKR request plan.", 403)
        identity = deepcopy(identity or {})
        if (identity.get("ticker") != ticker or identity.get("identity_status") != "verified"
                or any(not identity.get(key) for key in ("issuer_id", "instrument_id", "listing_id", "cik"))):
            fail("ibkr_identity_unverified", "An exact verified Fairworth issuer, instrument and listing identity is required.")
        if identity.get("security_form", identity.get("instrument_type")) not in {"common_stock", "domestic_common_stock", "reit", "financial_institution", "insurance"}:
            fail("ibkr_unsupported_instrument", "The initial IBKR adapter supports verified domestic ordinary stock only.")
        normalize_cik(identity["cik"])
        if identity.get("exchange_mic") not in VENUES:
            fail("ibkr_exchange_unverified", "The selected primary listing venue is not supported by this adapter.")
        if identity.get("quote_currency") is not None and not re.fullmatch(r"[A-Z]{3}", str(identity["quote_currency"])):
            fail("ibkr_missing_currency", "The selected listing's retained trading currency is invalid.")
        return ticker, identity

    async def _request(self, kind, operation):
        async with self._lock:
            maximum = getattr(self._authorization, {"contracts": "max_contract_lookups", "quote": "max_quotes", "history": "max_history_requests"}[kind])
            if self._counts[kind] >= maximum:
                fail("ibkr_request_budget_exhausted", "The approved IBKR request limit has been reached; no retry or fallback is performed.", 403)
            if self._last_start is not None:
                await asyncio.sleep(max(0, self.connection.minimum_interval_seconds - (asyncio.get_running_loop().time() - self._last_start)))
            self._last_start = asyncio.get_running_loop().time()
            self._counts[kind] += 1  # Failed and cancelled requests consume approval.
            try:
                return await asyncio.wait_for(operation(), self.connection.timeout_seconds)
            except TimeoutError:
                fail("ibkr_timeout", "The bounded IBKR request timed out; it was not retried.", 504)

    async def resolve_contract(self, ticker, identity=None):
        ticker, identity = self._scope(ticker, identity)
        key = json.dumps(identity, sort_keys=True, default=str)
        if key in self._contracts:
            return deepcopy(self._contracts[key])
        venues = VENUES[identity["exchange_mic"]]
        expected = {"symbol": ticker, "security_type": "STK", "exchange": "SMART",
                    "primary_exchange": sorted(venues - {"ISLAND"})[0], "currency": identity.get("quote_currency") or ""}
        matches = await self._request("contracts", lambda: self._transport.contracts(expected))
        if len(matches) != 1:
            fail("ibkr_ambiguous_contract" if matches else "ibkr_no_matching_contract", "The exact IBKR stock contract is ambiguous." if matches else "No matching IBKR stock contract was returned.")
        record = matches[0]
        if record.get("security_type") != "STK":
            fail("ibkr_unsupported_instrument", "The returned IBKR contract is not ordinary stock.")
        if record.get("symbol") != ticker or record.get("local_symbol") != ticker or record.get("primary_exchange") not in venues:
            fail("ibkr_contract_conflict", "IBKR symbol, local symbol or primary exchange conflicts with the selected listing.")
        if not re.fullmatch(r"[A-Z]{3}", str(record.get("currency", ""))):
            fail("ibkr_missing_currency", "The exact IBKR contract did not supply a usable trading currency.")
        if identity.get("quote_currency") and record.get("currency") != identity["quote_currency"]:
            fail("ibkr_currency_conflict", "IBKR trading currency conflicts with the source-backed selected listing currency.")
        if not isinstance(record.get("con_id"), int) or isinstance(record["con_id"], bool) or record["con_id"] <= 0 or not record.get("trading_class"):
            fail("ibkr_contract_incomplete", "IBKR contract identifier or trading-class metadata is unavailable.")
        expected_class = (identity.get("provider_symbols") or {}).get("ibkr_trading_class", ticker)
        if record["trading_class"] != expected_class:
            fail("ibkr_contract_conflict", "IBKR trading class conflicts with the selected class; no alternative instrument is substituted.")
        fields = ("con_id", "symbol", "local_symbol", "security_type", "exchange", "primary_exchange", "currency", "trading_class", "time_zone_id")
        result = {key: record.get(key) for key in fields}
        result.update(**PRIVATE, identity={key: identity.get(key) for key in ("issuer_id", "instrument_id", "listing_id", "cik", "ticker")},
                      retrieved_at=self._clock().isoformat(), data_origin="simulated_ibkr" if self._transport.simulated else "actual_ibkr",
                      identity_limitations=["IBKR conId is not SEC CIK, issuer ownership proof, or current listing proof."])
        self._contracts[key] = result
        return deepcopy(result)

    async def profile(self, ticker, identity=None):
        contract = await self.resolve_contract(ticker, identity)
        return {**contract, "ticker": ticker, "exchange": contract["primary_exchange"], "source_security": deepcopy(contract)}

    async def quote(self, ticker, identity=None):
        contract = await self.resolve_contract(ticker, identity)
        raw = await self._request("quote", lambda: self._transport.quote(contract, self._authorization.market_data_type))
        data_type = raw.get("market_data_type")
        if data_type not in DATA_TYPES:
            fail("ibkr_market_data_type_unverified", "IBKR did not identify whether this quote is live, frozen or delayed.")
        price = _number(raw.get("last"))
        if price is None:
            fail("ibkr_data_unavailable", "IBKR did not return a finite positive last-trade price.", 503)
        observed = _instant(raw.get("last_timestamp"))
        warnings = []
        if observed is None:
            warnings.append({"code": "ibkr_missing_source_timestamp", "field": "price_timestamp", "message": "The source supplied no last-trade timestamp; retrieval time does not establish a current quote."})
        elif observed > self._clock() + timedelta(minutes=5):
            fail("ibkr_future_source_timestamp", "The source trade timestamp is in the future.")
        result = {**PRIVATE, "ticker": ticker, "price": price, "bid": _number(raw.get("bid")), "ask": _number(raw.get("ask")),
                  "currency": contract["currency"], "exchange": contract["primary_exchange"], "price_timestamp": observed.isoformat() if observed else None,
                  "retrieved_at": self._clock().isoformat(), "market_data_type": DATA_TYPES[data_type], "market_data_type_id": data_type,
                  "current_comparison_eligible": data_type == 1 and observed is not None and 0 <= (self._clock() - observed).total_seconds() <= 300,
                  "source_security": contract, "identity": contract["identity"], "data_origin": contract["data_origin"], "warnings": warnings,
                  "session": {"connection": "local_tws_api", "market_session": "not_inferred", "account_information_collected": False}}
        if data_type != 1:
            warnings.append({"code": "ibkr_" + DATA_TYPES[data_type], "field": "price", "message": "This observation is not live market data."})
        result["observation_sha256"] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
        return result

    async def historical_prices(self, ticker, limit=31, identity=None):
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 31:
            fail("ibkr_history_limit", "The initial approved adapter is limited to one request of at most 31 calendar days.")
        contract = await self.resolve_contract(ticker, identity)
        raw = await self._request("history", lambda: self._transport.history(contract, limit))
        output = []
        seen = set()
        for row in raw:
            try:
                day = date.fromisoformat(str(row.get("date")))
            except ValueError:
                fail("ibkr_invalid_history", "An IBKR daily bar has no valid source period date.")
            if day in seen or day > self._clock().date() or day < self._clock().date() - timedelta(days=limit + 1):
                fail("ibkr_invalid_history", "The returned bars contain duplicate or out-of-request periods.")
            seen.add(day)
            if _number(row.get("close")) is None:
                fail("ibkr_invalid_history", "An IBKR daily bar has no usable closing price.")
            if row.get("what_to_show") != "TRADES":
                fail("ibkr_history_adjustment_unsupported", "Only documented split-adjusted, dividend-unadjusted TRADES daily bars are supported.")
            output.append({**PRIVATE, "date": day.isoformat(), "close": float(row["close"]), "currency": contract["currency"],
                           "source_security": contract, "identity": contract["identity"], "data_origin": contract["data_origin"],
                           "retrieved_at": self._clock().isoformat(), "observation_timestamp": None, "source_period": "daily_session_bar",
                           "session_close_time_verified": False, "bar_complete": None,
                           "adjustment_basis": "split_adjusted", "adjustment_date": self._clock().date().isoformat(),
                           "what_to_show": "TRADES", "split_history_complete": False,
                           "limitations": ["Daily source dates are not precise trade timestamps.", "IBKR historical bars do not establish a complete corporate-action or split-event history."]})
        return sorted(output, key=lambda item: item["date"], reverse=True)

    async def dividends(self, ticker, limit=100, identity=None):
        fail("ibkr_operation_unsupported", "The initial adapter does not request dividends, corporate actions, account or trading data.")
