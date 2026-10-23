"""Small asynchronous facade over the official, separately installed TWS SDK.

No package import or socket connection occurs until connect(). The supported
surface is contract metadata, bounded watchlist data, daily TRADES bars and their
cancellation. There is no account, positions, trading or order facade.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import importlib
import threading
import time

from app.providers.base import ProviderError


def ibkr_error(code):
    """Drop upstream text: it may contain account/session identifiers."""
    mapping = {
        502: ("ibkr_connection_refused", "TWS or IB Gateway is unavailable or its approved API socket is not accepting connections."),
        504: ("ibkr_session_unavailable", "The IBKR API session is not connected."),
        1100: ("ibkr_session_disconnected", "The IBKR session disconnected; no reconnect was attempted."),
        1300: ("ibkr_session_disconnected", "The IBKR API socket closed; no reconnect was attempted."),
        326: ("ibkr_client_id_in_use", "The approved nonzero IBKR API client identifier is already in use."),
        200: ("ibkr_no_matching_contract", "IBKR could not resolve this exact stock contract."),
        354: ("ibkr_subscription_missing", "The session lacks the required API market-data subscription."),
        10089: ("ibkr_subscription_missing", "The session lacks the required API market-data subscription."),
        10090: ("ibkr_subscription_missing", "The requested API market data is only partially subscribed."),
        10167: ("ibkr_subscription_missing", "IBKR reports the live subscription is missing; no delayed fallback was requested."),
        10168: ("ibkr_subscription_missing", "IBKR reports the requested delayed data is not enabled."),
        10186: ("ibkr_subscription_missing", "IBKR reports that the requested market data is not subscribed."),
        100: ("ibkr_pacing_violation", "IBKR rejected the request rate; no retry was attempted."),
        420: ("ibkr_pacing_violation", "IBKR reported a pacing violation; no retry was attempted."),
        # Code 162 also covers entitlement/no-data failures; do not infer pacing.
        162: ("ibkr_historical_data_unavailable", "IBKR rejected historical data; permissions, availability or pacing require local review."),
        165: ("ibkr_data_unavailable", "IBKR has no historical data for this request."),
        366: ("ibkr_data_unavailable", "The bounded IBKR historical request is unavailable."),
    }
    label, message = mapping.get(code, ("ibkr_request_failed", "The bounded IBKR market-data request failed; no retry was attempted."))
    return ProviderError(label, message, 503)


def make_bridge(EClient, EWrapper):
    """SDK callbacks retain only whitelisted contract/market fields."""
    class Bridge(EWrapper, EClient):
        def __init__(self):
            EWrapper.__init__(self)
            EClient.__init__(self, self)
            self.ready = threading.Event()
            self.done = threading.Event()
            self.records = []
            self.quote_record = {}
            self.failure = None
            self.active_id = None
            self.operation = None

        def reset(self, request_id, operation):
            self.active_id, self.operation = request_id, operation
            self.records, self.quote_record, self.failure = [], {}, None
            self.done.clear()

        def logAnswer(self, *_args, **_kwargs):
            pass

        def logRequest(self, *_args, **_kwargs):
            pass

        def nextValidId(self, _order_id):
            # Handshake completion only; never retain or request an order ID.
            self.ready.set()

        def error(self, reqId, *args):
            # The official API added errorTime in newer supported releases.
            code = args[1] if len(args) >= 3 and isinstance(args[1], int) else args[0] if args else None
            if code in {2104, 2106, 2107, 2108, 2158, 1101, 1102}:
                return
            if reqId in {-1, self.active_id}:
                self.failure = ibkr_error(code)
                self.done.set()
                self.ready.set()

        def connectionClosed(self):
            self.failure = ibkr_error(1100)
            self.done.set()
            self.ready.set()

        def contractDetails(self, reqId, detail):
            if reqId != self.active_id or self.operation != "contracts":
                return
            if len(self.records) >= 20:
                self.failure = ProviderError("ibkr_ambiguous_contract", "The contract lookup exceeds the bounded exact-match result limit.", 422)
                self.done.set()
                return
            c = detail.contract
            self.records.append({"con_id": c.conId, "symbol": c.symbol, "local_symbol": c.localSymbol,
                                 "security_type": c.secType, "exchange": c.exchange, "primary_exchange": c.primaryExchange,
                                 "currency": c.currency, "trading_class": c.tradingClass, "time_zone_id": detail.timeZoneId})

        def contractDetailsEnd(self, reqId):
            if reqId == self.active_id:
                self.done.set()

        def marketDataType(self, reqId, marketDataType):
            if reqId == self.active_id:
                self.quote_record["market_data_type"] = marketDataType

        def tickPrice(self, reqId, tickType, price, _attrib):
            if reqId != self.active_id or self.operation != "quote":
                return
            fields = {1: "bid", 2: "ask", 4: "last", 66: "delayed_bid", 67: "delayed_ask", 68: "delayed_last"}
            if tickType in fields:
                self.quote_record[fields[tickType]] = price

        def tickString(self, reqId, tickType, value):
            if reqId == self.active_id and self.operation == "quote" and tickType in {45, 88}:
                try:
                    stamp = datetime.fromtimestamp(int(value), UTC).isoformat()
                except (ValueError, TypeError, OverflowError, OSError):
                    return
                self.quote_record["last_timestamp" if tickType == 45 else "delayed_last_timestamp"] = stamp

        def historicalData(self, reqId, bar):
            if reqId != self.active_id or self.operation != "history":
                return
            if len(self.records) >= 32:
                self.failure = ProviderError("ibkr_history_limit", "Historical data exceeds the approved bounded daily-bar count.", 422)
                self.done.set()
                return
            try:
                day = datetime.strptime(str(bar.date), "%Y%m%d").date().isoformat()
            except ValueError:
                day = None
            self.records.append({"date": day, "close": bar.close, "what_to_show": "TRADES"})

        def historicalDataEnd(self, reqId, _start, _end):
            if reqId == self.active_id:
                self.done.set()

    # EWrapper's defaults can log callback arguments. Ignore every callback not
    # explicitly required above, including automatically announced managedAccounts
    # and any unsolicited account/order/position messages. No payload is retained.
    def ignored(*_args, **_kwargs):
        pass

    allowed_callbacks = {"error", "connectionClosed", "nextValidId", "contractDetails", "contractDetailsEnd",
                         "marketDataType", "tickPrice", "tickString", "historicalData", "historicalDataEnd"}
    for name, method in vars(EWrapper).items():
        if callable(method) and not name.startswith("_") and name not in allowed_callbacks:
            setattr(Bridge, name, ignored)

    def prohibited(*_args, **_kwargs):
        raise ProviderError("ibkr_operation_unsupported", "Only approved contract and market-data operations are permitted.", 403)

    # Deny all additional outbound req*, cancel*, order/account operations even
    # on the internal SDK object. Explicit SDK handshake functions remain intact.
    allowed_requests = {"reqContractDetails", "reqMarketDataType", "reqMktData", "cancelMktData", "reqHistoricalData", "cancelHistoricalData"}
    allowed_requests |= {name + "ProtoBuf" for name in tuple(allowed_requests)}
    for name, method in vars(EClient).items():
        if callable(method) and (name.startswith(("req", "cancel")) or name in {"placeOrder", "exerciseOptions", "replaceFA", "updateDisplayGroup"}) and name not in allowed_requests:
            setattr(Bridge, name, prohibited)
    return Bridge


class OfficialIbkrTransport:
    simulated = False

    def __init__(self, timeout=15):
        self.timeout = min(30, max(1, timeout))
        self._app = None
        self._reader = None
        self._request_id = 68000
        self._contract_type = None

    async def connect(self, connection):
        if self._app is not None:
            raise ProviderError("ibkr_not_authorized", "This bounded transport cannot reconnect automatically.", 403)
        try:
            client = importlib.import_module("ibapi.client").EClient
            wrapper = importlib.import_module("ibapi.wrapper").EWrapper
            self._contract_type = importlib.import_module("ibapi.contract").Contract
        except ImportError:
            raise ProviderError("ibkr_sdk_unavailable", "Install the official supported IBKR TWS Python API locally after reviewing its license; no package is downloaded automatically.", 503) from None
        self._app = make_bridge(client, wrapper)()
        try:
            await asyncio.wait_for(asyncio.to_thread(self._app.connect, connection.host, connection.port, connection.client_id), self.timeout)
            if not self._app.isConnected():
                raise ibkr_error(502)
            self._reader = threading.Thread(target=self._app.run, name="fairworth-ibkr-read-only", daemon=True)
            self._reader.start()
            ready = await asyncio.to_thread(self._app.ready.wait, self.timeout)
            if self._app.failure:
                raise self._app.failure
            if not ready:
                raise ProviderError("ibkr_session_unavailable", "The API handshake did not complete within the approved timeout.", 503)
        except (OSError, TimeoutError):
            await self.close()
            raise ibkr_error(502) from None
        except BaseException:
            await self.close()
            raise

    async def close(self):
        if self._app:
            self._app.disconnect()
        if self._reader and self._reader.is_alive():
            await asyncio.to_thread(self._reader.join, 1)

    def _contract(self, fields):
        contract = self._contract_type()
        for target, key in (("conId", "con_id"), ("symbol", "symbol"), ("localSymbol", "local_symbol"), ("secType", "security_type"),
                            ("primaryExchange", "primary_exchange"), ("currency", "currency"), ("tradingClass", "trading_class")):
            if fields.get(key) is not None:
                setattr(contract, target, fields[key])
        contract.exchange = "SMART"
        return contract

    def _begin(self, operation):
        if not self._app or not self._app.isConnected():
            raise ibkr_error(504)
        self._request_id += 1
        self._app.reset(self._request_id, operation)
        return self._request_id

    async def _wait(self):
        completed = await asyncio.to_thread(self._app.done.wait, self.timeout)
        if self._app.failure:
            raise self._app.failure
        if not completed:
            raise ProviderError("ibkr_timeout", "The bounded IBKR request timed out and was not retried.", 504)

    async def contracts(self, request):
        request_id = self._begin("contracts")
        self._app.reqContractDetails(request_id, self._contract(request))
        await self._wait()
        return list(self._app.records)

    async def quote(self, contract, market_data_type):
        request_id = self._begin("quote")
        self._app.reqMarketDataType(market_data_type)
        # Bounded ordinary streaming, cancelled after <=12 seconds. Never a
        # chargeable regulatory snapshot; no generic tick subscription required.
        self._app.reqMktData(request_id, self._contract(contract), "", False, False, [])
        try:
            deadline = time.monotonic() + min(12, self.timeout)
            while time.monotonic() < deadline:
                if self._app.failure:
                    raise self._app.failure
                raw = self._app.quote_record
                delayed = raw.get("market_data_type") in {3, 4}
                prefix = "delayed_" if delayed else ""
                if raw.get("market_data_type") and raw.get(prefix + "last") and raw.get(prefix + "last_timestamp"):
                    break
                await asyncio.sleep(.05)
            raw = dict(self._app.quote_record)
            prefix = "delayed_" if raw.get("market_data_type") in {3, 4} else ""
            return {key: raw.get(prefix + key) for key in ("last", "bid", "ask", "last_timestamp")} | {"market_data_type": raw.get("market_data_type")}
        finally:
            self._app.cancelMktData(request_id)

    async def history(self, contract, days):
        request_id = self._begin("history")
        self._app.reqHistoricalData(request_id, self._contract(contract), "", f"{days} D", "1 day", "TRADES", 1, 1, False, [])
        try:
            await self._wait()
            return list(self._app.records)
        finally:
            self._app.cancelHistoricalData(request_id)
