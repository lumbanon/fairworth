"""Deterministic broker simulations; no IBKR subscription/session is exercised."""
import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import socket
import ipaddress

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.ai.report_service import ResearchService
from app.core.config import Settings
from app.core.database import utcnow
from app.main import create_app
from app.models import CacheEntry
from app.providers.base import ProviderError
from app.providers.ibkr import IbkrAuthorization, IbkrConnection, IbkrMarketDataProvider, PRIVATE
from app.providers.ibkr_transport import OfficialIbkrTransport, ibkr_error, make_bridge
from app.providers.permitted_use import require_public_data
from app.services.cache_service import CacheService

CLOCK = datetime(2026, 10, 22, 14, 30, tzinfo=UTC)
IDENTITY = {"ticker": "AAPL", "cik": "0000320193", "issuer_id": "synthetic-issuer", "instrument_id": "synthetic-instrument",
            "listing_id": "synthetic-listing", "identity_status": "verified", "security_form": "common_stock", "exchange_mic": "XNAS", "quote_currency": "USD"}
CONTRACT = {"con_id": 123, "symbol": "AAPL", "local_symbol": "AAPL", "security_type": "STK", "exchange": "SMART",
            "primary_exchange": "NASDAQ", "currency": "USD", "trading_class": "AAPL", "time_zone_id": "US/Eastern"}


@pytest.fixture(autouse=True)
def no_broker_sockets(monkeypatch):
    original = socket.socket.connect
    def blocked(sock, address, *_args, **_kwargs):
        # Windows asyncio uses a loopback socketpair internally. Permit only that
        # infrastructure; all external addresses and broker ports stay blocked.
        if isinstance(address, tuple) and (not ipaddress.ip_address(address[0]).is_loopback or address[1] in {7496, 7497, 4001, 4002}):
            pytest.fail("No external or IBKR socket connection is permitted in offline tests.")
        return original(sock, address)
    monkeypatch.setattr(socket.socket, "connect", blocked)


class SimulatedIbkr:
    simulated = True
    def __init__(self):
        self.calls = []
        self.contract_rows = [deepcopy(CONTRACT)]
        self.quote_row = {"last": 100.125, "bid": 100.1, "ask": 100.15, "last_timestamp": CLOCK.isoformat(), "market_data_type": 1}
        self.bar_rows = [{"date": "2026-10-21", "close": 99.5, "what_to_show": "TRADES"}]
        self.failure = None

    async def connect(self, connection):
        self.calls.append(("connect", connection.port))
        if self.failure:
            raise self.failure

    async def close(self):
        self.calls.append(("close",))

    async def contracts(self, request):
        self.calls.append(("contracts", request))
        return deepcopy(self.contract_rows)

    async def quote(self, contract, market_data_type):
        self.calls.append(("quote", contract["con_id"], market_data_type))
        if self.failure:
            raise self.failure
        return deepcopy(self.quote_row)

    async def history(self, contract, days):
        self.calls.append(("history", contract["con_id"], days))
        return deepcopy(self.bar_rows)


def authorization(**changes):
    return IbkrAuthorization(approval_reference="offline-synthetic-permission", symbols=("AAPL",),
        personal_use_confirmed=True, api_non_display_use_confirmed=True, read_only_session_confirmed=True, **changes)


async def provider(monkeypatch, transport=None, **auth_changes):
    # Eliminate only simulated pacing waits; production still enforces >=1s.
    async def no_wait(_seconds): pass
    monkeypatch.setattr("app.providers.ibkr.asyncio.sleep", no_wait)
    transport = transport or SimulatedIbkr()
    result = IbkrMarketDataProvider(IbkrConnection(port=7497), transport=transport, clock=lambda: CLOCK)
    await result.open(authorization(**auth_changes))
    return result, transport


def test_construction_and_configuration_never_connect_or_enable():
    transport = SimulatedIbkr()
    p = IbkrMarketDataProvider(transport=transport)
    assert not p.enabled and transport.calls == [] and p.connection.port is None
    settings = Settings(_env_file=None)
    assert settings.market_data_provider == "disabled" and settings.ibkr_port is None
    with pytest.raises(ValidationError):
        Settings(_env_file=None, market_data_provider="ibkr")


@pytest.mark.parametrize("host", ["localhost", "0.0.0.0", "192.168.1.10", "8.8.8.8", "https://127.0.0.1"])
def test_connection_rejects_dns_remote_and_public_hosts(host):
    with pytest.raises(ValidationError):
        IbkrConnection(host=host, port=7497)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ibkr_host=host)


@pytest.mark.asyncio
async def test_unapproved_session_and_unset_port_fail_before_transport():
    transport = SimulatedIbkr()
    p = IbkrMarketDataProvider(transport=transport)
    with pytest.raises(ProviderError, match="approved") as caught:
        await p.open(authorization())
    assert caught.value.code == "ibkr_not_authorized" and not transport.calls
    p = IbkrMarketDataProvider(IbkrConnection(port=7497), transport=transport)
    with pytest.raises(ProviderError):
        await p.open(authorization().model_copy(update={"personal_use_confirmed": False}))
    assert not transport.calls


@pytest.mark.asyncio
async def test_no_implicit_connect_on_quote():
    p = IbkrMarketDataProvider(transport=SimulatedIbkr())
    with pytest.raises(ProviderError) as caught:
        await p.quote("AAPL", IDENTITY)
    assert caught.value.code == "ibkr_not_authorized"


@pytest.mark.asyncio
async def test_contract_quote_identity_clocks_and_private_source(monkeypatch):
    p, t = await provider(monkeypatch)
    result = await p.quote("AAPL", IDENTITY)
    assert result["price"] == 100.125 and result["price_timestamp"] == CLOCK.isoformat()
    assert result["retrieved_at"] == CLOCK.isoformat() and result["source_security"]["con_id"] == 123
    assert result["currency"] == "USD" and result["market_data_type"] == "live"
    assert result["current_comparison_eligible"] and result["data_origin"] == "simulated_ibkr"
    assert result["identity"]["cik"] == IDENTITY["cik"]
    assert result["permitted_use"] == "personal_local_only" and result["public_redistribution_allowed"] is False
    assert len([call for call in t.calls if call[0] == "contracts"]) == 1
    assert len(result["observation_sha256"]) == 64
    await p.close()
    assert not p.enabled


@pytest.mark.asyncio
async def test_currency_can_come_from_exact_contract_without_venue_or_accounting_inference(monkeypatch):
    p, _ = await provider(monkeypatch)
    identity = {key: value for key, value in IDENTITY.items() if key != "quote_currency"}
    result = await p.quote("AAPL", {**identity, "reporting_currency": "EUR"})
    assert result["currency"] == "USD"  # Explicit exact-contract source, no conversion.


@pytest.mark.parametrize("rows,code", [([], "ibkr_no_matching_contract"), ([CONTRACT, CONTRACT], "ibkr_ambiguous_contract"),
    ([{**CONTRACT, "primary_exchange": "NYSE"}], "ibkr_contract_conflict"),
    ([{**CONTRACT, "currency": "EUR"}], "ibkr_currency_conflict"),
    ([{**CONTRACT, "currency": ""}], "ibkr_missing_currency"),
    ([{**CONTRACT, "symbol": "MSFT"}], "ibkr_contract_conflict"),
    ([{**CONTRACT, "security_type": "OPT"}], "ibkr_unsupported_instrument"),
    ([{**CONTRACT, "trading_class": "WRONG"}], "ibkr_contract_conflict"),
    ([{**CONTRACT, "con_id": 0}], "ibkr_contract_incomplete")])
@pytest.mark.asyncio
async def test_contract_conflicts_fail_closed(monkeypatch, rows, code):
    t = SimulatedIbkr()
    t.contract_rows = deepcopy(rows)
    p, _ = await provider(monkeypatch, t)
    with pytest.raises(ProviderError) as caught:
        await p.quote("AAPL", IDENTITY)
    assert caught.value.code == code
    assert not any(call[0] == "quote" for call in t.calls)


@pytest.mark.parametrize("change,code", [({"instrument_id": None}, "ibkr_identity_unverified"),
    ({"identity_status": "ambiguous"}, "ibkr_identity_unverified"), ({"security_form": "etf"}, "ibkr_unsupported_instrument"),
    ({"exchange_mic": "UNKNOWN"}, "ibkr_exchange_unverified")])
@pytest.mark.asyncio
async def test_registry_scope_cannot_be_replaced_by_conid(monkeypatch, change, code):
    p, t = await provider(monkeypatch)
    with pytest.raises(ProviderError) as caught:
        await p.quote("AAPL", {**IDENTITY, **change})
    assert caught.value.code == code and len(t.calls) == 1


@pytest.mark.parametrize("data_type,label", [(1, "live"), (2, "frozen"), (3, "delayed"), (4, "delayed_frozen")])
@pytest.mark.asyncio
async def test_source_market_data_type_not_requested_type_controls_state(monkeypatch, data_type, label):
    t = SimulatedIbkr()
    t.quote_row["market_data_type"] = data_type
    p, _ = await provider(monkeypatch, t)
    result = await p.quote("AAPL", IDENTITY)
    assert result["market_data_type"] == label
    assert result["current_comparison_eligible"] is (data_type == 1)


@pytest.mark.asyncio
async def test_missing_timestamp_never_uses_retrieval_time(monkeypatch):
    t = SimulatedIbkr()
    t.quote_row["last_timestamp"] = None
    p, _ = await provider(monkeypatch, t)
    result = await p.quote("AAPL", IDENTITY)
    assert result["price_timestamp"] is None and not result["current_comparison_eligible"]
    assert result["warnings"][0]["code"] == "ibkr_missing_source_timestamp"


@pytest.mark.parametrize("change,code", [({"last": None}, "ibkr_data_unavailable"), ({"last": float("nan")}, "ibkr_data_unavailable"),
    ({"market_data_type": None}, "ibkr_market_data_type_unverified"),
    ({"last_timestamp": (CLOCK + timedelta(hours=1)).isoformat()}, "ibkr_future_source_timestamp")])
@pytest.mark.asyncio
async def test_invalid_quotes_never_publish_comparison(monkeypatch, change, code):
    t = SimulatedIbkr()
    t.quote_row.update(change)
    p, _ = await provider(monkeypatch, t)
    with pytest.raises(ProviderError) as caught:
        await p.quote("AAPL", IDENTITY)
    assert caught.value.code == code


@pytest.mark.parametrize("upstream,expected", [(502, "ibkr_connection_refused"), (504, "ibkr_session_unavailable"),
    (354, "ibkr_subscription_missing"), (10089, "ibkr_subscription_missing"), (420, "ibkr_pacing_violation"),
    (100, "ibkr_pacing_violation"), (1100, "ibkr_session_disconnected"), (162, "ibkr_historical_data_unavailable")])
@pytest.mark.asyncio
async def test_safe_error_categories_and_no_retry(monkeypatch, upstream, expected):
    p, t = await provider(monkeypatch)
    t.failure = ibkr_error(upstream)
    with pytest.raises(ProviderError) as caught:
        await p.quote("AAPL", IDENTITY)
    assert caught.value.code == expected
    with pytest.raises(ProviderError) as again:
        await p.quote("AAPL", IDENTITY)
    assert again.value.code == "ibkr_request_budget_exhausted"
    assert len([call for call in t.calls if call[0] == "quote"]) == 1


@pytest.mark.asyncio
async def test_gateway_connection_failure_never_enables_or_reconnects(monkeypatch):
    t = SimulatedIbkr()
    t.failure = ibkr_error(502)
    p = IbkrMarketDataProvider(IbkrConnection(port=7497), transport=t)
    with pytest.raises(ProviderError):
        await p.open(authorization())
    assert not p.enabled
    with pytest.raises(ProviderError) as caught:
        await p.open(authorization())
    assert caught.value.code == "ibkr_request_budget_exhausted" and len(t.calls) == 1


@pytest.mark.asyncio
async def test_history_documents_adjustment_and_never_claims_split_completeness(monkeypatch):
    p, _ = await provider(monkeypatch, max_history_requests=1)
    bars = await p.historical_prices("AAPL", 31, IDENTITY)
    assert bars[0]["date"] == "2026-10-21" and bars[0]["observation_timestamp"] is None
    assert bars[0]["adjustment_basis"] == "split_adjusted" and not bars[0]["split_history_complete"]
    assert bars[0]["currency"] == "USD" and bars[0]["data_origin"] == "simulated_ibkr"


@pytest.mark.parametrize("change,code", [({"what_to_show": "ADJUSTED_LAST"}, "ibkr_history_adjustment_unsupported"),
    ({"date": None}, "ibkr_invalid_history"), ({"close": -1}, "ibkr_invalid_history")])
@pytest.mark.asyncio
async def test_history_adjustment_and_period_errors_fail_closed(monkeypatch, change, code):
    t = SimulatedIbkr()
    t.bar_rows[0].update(change)
    p, _ = await provider(monkeypatch, t, max_history_requests=1)
    with pytest.raises(ProviderError) as caught:
        await p.historical_prices("AAPL", 31, IDENTITY)
    assert caught.value.code == code


@pytest.mark.asyncio
async def test_unapproved_symbol_history_and_dividends_do_not_request(monkeypatch):
    p, t = await provider(monkeypatch)
    with pytest.raises(ProviderError):
        await p.quote("MSFT", {**IDENTITY, "ticker": "MSFT"})
    with pytest.raises(ProviderError):
        await p.historical_prices("AAPL", 31, IDENTITY)
    with pytest.raises(ProviderError):
        await p.dividends("AAPL", identity=IDENTITY)
    assert not any(call[0] in {"quote", "history"} for call in t.calls)
    assert not hasattr(p, "placeOrder") and not hasattr(p, "reqPositions") and not hasattr(t, "placeOrder")


class FakeWrapper:
    def managedAccounts(self, value):
        raise AssertionError("Private account callback must be ignored")
    def openOrder(self, *values):
        raise AssertionError("Private order callback must be ignored")
    def logAnswer(self, *_args): pass


class FakeClient:
    def __init__(self, wrapper): self.wrapper = wrapper
    def placeOrder(self, *args): raise AssertionError("Trading must never be dispatched")
    def reqPositions(self): raise AssertionError("Positions must never be requested")
    def reqManagedAccts(self): raise AssertionError("Accounts must never be requested")
    def reqMktData(self, *_args): pass
    def reqMktDataProtoBuf(self, *_args): pass


def test_official_bridge_discards_unsolicited_account_callbacks_and_blocks_order_api():
    b = make_bridge(FakeClient, FakeWrapper)()
    b.managedAccounts("private-test-account-never-retained")
    b.openOrder("private-test-order-never-retained")
    assert "private-test-account" not in repr(b.__dict__) and "private-test-order" not in repr(b.__dict__)
    for operation in (b.placeOrder, b.reqPositions, b.reqManagedAccts):
        with pytest.raises(ProviderError) as caught:
            operation()
        assert caught.value.code == "ibkr_operation_unsupported"
    b.reqMktDataProtoBuf(None)  # Official modern transport helper remains usable.


@pytest.mark.parametrize("new_signature", [False, True])
def test_sdk_error_text_is_never_retained(new_signature):
    b = make_bridge(FakeClient, FakeWrapper)()
    b.reset(68, "quote")
    args = (68, 1234567890, 354, "private-test-session-detail") if new_signature else (68, 354, "private-test-session-detail")
    b.error(*args)
    assert b.failure.code == "ibkr_subscription_missing" and "private-test-session" not in repr(b.__dict__)


@pytest.mark.asyncio
async def test_optional_sdk_is_not_downloaded_if_unavailable(monkeypatch):
    def missing(_name): raise ImportError()
    monkeypatch.setattr("app.providers.ibkr_transport.importlib.import_module", missing)
    transport = OfficialIbkrTransport()
    with pytest.raises(ProviderError) as caught:
        await transport.connect(IbkrConnection(port=7497))
    assert caught.value.code == "ibkr_sdk_unavailable"


@pytest.mark.parametrize("payload", [PRIVATE, {"derived": {"sources": [PRIVATE]}}, {"provider": "fixture", "source_provider": "ibkr"},
    {"permitted_use": "personal_local_only"}, {"public_redistribution_allowed": False}])
def test_private_data_classification_blocks_nested_public_exports(payload):
    with pytest.raises(ProviderError) as caught:
        require_public_data(payload)
    assert caught.value.code == "personal_market_data_restricted"


@pytest.mark.asyncio
async def test_shared_cache_rejects_private_writes_and_preexisting_private_reads(session_factory):
    cache = CacheService(session_factory)
    with pytest.raises(ProviderError):
        cache._write("test:private", {**PRIVATE, "price": 100}, 30, "fixture")
    assert cache._read("test:private") is None
    with session_factory.begin() as session:
        session.add(CacheEntry(key="test:private", provider="fixture", payload={"derived": PRIVATE}, retrieved_at=utcnow(), expires_at=utcnow() + timedelta(minutes=1)))
    for read in (cache._read, cache._read_fresh):
        with pytest.raises(ProviderError): read("test:private")
    with pytest.raises(ProviderError):
        await cache.get_or_load("test:private", 30, "fixture", lambda: asyncio.sleep(0, result={"price": 1}))


def test_injected_ibkr_provider_cannot_connect_from_public_api(engine, fake_providers):
    sec, fake = fake_providers
    fake.name = "ibkr"
    with TestClient(create_app(Settings(_env_file=None), engine=engine, providers=(sec, fake))) as client:
        body = client.get("/api/stocks/MSFT").json()
        assert body["market"] is None and fake.quote_calls == 0
        assert any(item["code"] == "personal_market_data_restricted" for item in body["warnings"])


def test_mislabeled_private_quote_never_enters_public_response_or_cache(engine, session_factory, fake_providers):
    sec, fake = fake_providers
    async def quote(ticker):
        return {**PRIVATE, "ticker": ticker, "price": 98765, "currency": "USD", "price_timestamp": CLOCK.isoformat()}
    fake.quote = quote
    with TestClient(create_app(Settings(_env_file=None), engine=engine, providers=(sec, fake))) as client:
        response = client.get("/api/stocks/MSFT")
        assert response.status_code == 200 and response.json()["market"] is None and "98765" not in response.text
    assert CacheService(session_factory)._read("market:fixture-market:quote:MSFT") is None


@pytest.mark.asyncio
async def test_personal_derived_values_cannot_be_exported_to_ai():
    class PrivateAssembler:
        async def assemble(self, *_args, **_kwargs):
            return {"ticker": "AAPL", "registry": {"e1": {"value": 98765, "derivation": {"sources": [PRIVATE]}}}}
    service = ResearchService(Settings(_env_file=None), PrivateAssembler(), SimpleNamespace())
    with pytest.raises(ProviderError) as caught:
        await service._context("AAPL", None)
    assert caught.value.code == "personal_market_data_restricted" and not service.snapshots


def test_private_file_exports_are_scoped_and_immutable(tmp_path, monkeypatch):
    from scripts import ibkr_local_research as cli
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    with pytest.raises(ValueError): cli.private_output(tmp_path / "public.json")
    private = tmp_path / ".phase68.local" / "one.json"
    assert cli.private_output(private) == private
    private.parent.mkdir()
    private.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError): cli.private_output(private)


@pytest.mark.asyncio
async def test_cli_plan_has_no_connection_or_registry_access(capsys, monkeypatch):
    from scripts import ibkr_local_research as cli
    import json
    monkeypatch.setattr(cli, "Settings", lambda: Settings(_env_file=None))
    args = SimpleNamespace(symbol="AAPL", instrument_id="synthetic-instrument", listing_id="synthetic-listing", history_days=None, market_data_type=1, output=None, connect=False)
    await cli.execute(args)
    plan = json.loads(capsys.readouterr().out)
    assert plan["status"] == "not_connected" and plan["plan"]["port"] is None
    assert plan["plan"]["account_requests"] == plan["plan"]["trading_requests"] == 0


@pytest.mark.asyncio
async def test_non_display_permission_is_required_separately():
    p = IbkrMarketDataProvider(IbkrConnection(port=7497), transport=SimulatedIbkr())
    with pytest.raises(ProviderError) as caught:
        await p.open(authorization().model_copy(update={"api_non_display_use_confirmed": False}))
    assert caught.value.code == "ibkr_not_authorized"


def test_source_origin_cannot_be_laundered_by_dropping_provider_name():
    with pytest.raises(ProviderError):
        require_public_data({"value": 100, "data_origin": "actual_ibkr"})


class TransportClient(FakeClient):
    def connect(self, *_args):
        self.connected = True
        self.calls = []
        self.nextValidId(999)
    def run(self): pass
    def isConnected(self): return getattr(self, "connected", False)
    def disconnect(self): self.connected = False
    def reqContractDetails(self, req_id, contract):
        self.calls.append(("contracts", contract.symbol, contract.primaryExchange, contract.currency))
        self.contractDetails(req_id, SimpleNamespace(contract=SimpleNamespace(conId=123, symbol="AAPL", localSymbol="AAPL", secType="STK",
            exchange="SMART", primaryExchange="NASDAQ", currency="USD", tradingClass="AAPL"), timeZoneId="US/Eastern"))
        self.contractDetailsEnd(req_id)
    def reqMarketDataType(self, value): self.requested_type = value
    def reqMktData(self, req_id, contract, generic, snapshot, regulatory, options):
        self.calls.append(("quote", generic, snapshot, regulatory))
        self.marketDataType(req_id, 3)
        self.tickPrice(req_id, 4, 999, None)  # Separate live data is not mixed.
        self.tickString(req_id, 45, str(int(CLOCK.timestamp()) + 30))
        self.tickPrice(req_id, 68, 100, None)
        self.tickString(req_id, 88, str(int(CLOCK.timestamp())))
    def cancelMktData(self, req_id): self.calls.append(("cancel_quote",))
    def reqHistoricalData(self, req_id, contract, end, duration, bar_size, what, rth, fmt, update, options):
        self.calls.append(("history", duration, bar_size, what, rth, update))
        self.historicalData(req_id, SimpleNamespace(date="20261021", close=99.5))
        self.historicalDataEnd(req_id, "", "")
    def cancelHistoricalData(self, req_id): self.calls.append(("cancel_history",))


@pytest.mark.asyncio
async def test_official_sdk_facade_operations_with_simulated_callbacks(monkeypatch):
    modules = {"ibapi.client": SimpleNamespace(EClient=TransportClient), "ibapi.wrapper": SimpleNamespace(EWrapper=FakeWrapper),
               "ibapi.contract": SimpleNamespace(Contract=SimpleNamespace)}
    monkeypatch.setattr("app.providers.ibkr_transport.importlib.import_module", lambda name: modules[name])
    t = OfficialIbkrTransport(timeout=1)
    await t.connect(IbkrConnection(port=7497))
    contracts = await t.contracts(CONTRACT)
    result = await t.quote(contracts[0], 1)
    bars = await t.history(contracts[0], 31)
    assert result == {"last": 100, "bid": None, "ask": None, "last_timestamp": CLOCK.isoformat(), "market_data_type": 3}
    assert bars == [{"date": "2026-10-21", "close": 99.5, "what_to_show": "TRADES"}]
    assert ("quote", "", False, False) in t._app.calls
    assert ("history", "31 D", "1 day", "TRADES", 1, False) in t._app.calls
    assert ("cancel_quote",) in t._app.calls and ("cancel_history",) in t._app.calls
    await t.close()
