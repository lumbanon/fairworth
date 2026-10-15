"""Deterministic provider boundaries; no live contact or real key is used."""
import asyncio
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest

from app.core.config import Settings
from app.core.database import utcnow
from app.models import CacheEntry
from app.providers.base import ProviderError
from app.providers.market_data import FmpMarketDataProvider
from app.providers.sec_edgar import SecEdgarProvider
from app.providers.treasury import TreasuryYieldProvider
from app.services.automatic_inputs_service import AutomaticInputsService, latest_sec_shares, original_annual_periods
from app.services.cache_service import CacheService, CachedResult
from app.services.normalization import normalize_company_facts


def xml(rows):
    return '<feed xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata" xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices">' + ''.join(
        f'<entry><m:properties><d:NEW_DATE>{day}</d:NEW_DATE><d:BC_10YEAR>{value}</d:BC_10YEAR></m:properties></entry>' for day, value in rows) + '</feed>'


def annual_observation(value, *, unit="USD", start="2024-01-01", end="2024-12-31", filed="2025-02-15", accession="0000000001-25-000001", fy=2024):
    row = {"val": value, "end": end, "filed": filed, "accn": accession, "form": "10-K", "fp": "FY", "fy": fy}
    if start:
        row["start"] = start
    return {"units": {unit: [row]}}


def raw_annual():
    return {"cik": 1, "facts": {"us-gaap": {
        "Revenues": annual_observation(1000), "NetIncomeLoss": annual_observation(100),
        "EarningsPerShareDiluted": annual_observation(10, unit="USD/shares"),
        "WeightedAverageNumberOfDilutedSharesOutstanding": annual_observation(10, unit="shares"),
    }}}


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-6", "26", "garbage"])
def test_treasury_rejects_nonfinite_invalid_or_out_of_supported_bounds_yield(value):
    assert TreasuryYieldProvider.parse(xml([("2025-01-02", value)]), date(2025, 1, 3)) == []


def test_treasury_observation_date_percent_conversion_and_future_exclusion():
    rows = TreasuryYieldProvider.parse(xml([("2025-01-02", "4.25"), ("2025-01-03", "4.5")]), date(2025, 1, 2))
    assert len(rows) == 1
    assert rows[0]["value"] == .0425
    assert rows[0]["observation_date"] == "2025-01-02"
    assert rows[0]["unit"] == "fraction"
    assert rows[0]["maturity_years"] == 10


@pytest.mark.parametrize("value,expected", [("0", 0), ("-1", -.01)])
def test_treasury_preserves_verified_zero_or_supported_negative_observation(value, expected):
    rows = TreasuryYieldProvider.parse(xml([("2025-01-02", value)]), date(2025, 1, 3))
    assert rows[0]["value"] == expected


@pytest.mark.parametrize("payload", ["not XML", '<!DOCTYPE x [<!ENTITY secret SYSTEM "file:///private">]><feed/>'])
def test_treasury_xml_rejects_invalid_payload_and_entities(payload):
    with pytest.raises(ProviderError) as captured:
        TreasuryYieldProvider.parse(payload, date(2025, 1, 2))
    assert captured.value.code == "invalid_provider_response"


def test_treasury_conflicting_same_day_observations_are_unavailable():
    with pytest.raises(ProviderError):
        TreasuryYieldProvider.parse(xml([("2025-01-02", "4.25"), ("2025-01-02", "4.5")]), date(2025, 1, 2))


@pytest.mark.asyncio
async def test_treasury_month_boundary_uses_last_published_prior_month():
    requests = []
    def handle(request):
        requests.append(request)
        month = request.url.params["field_tdr_date_value_month"]
        return httpx.Response(200, text=xml([] if month == "202502" else [("2025-01-31", "4.5")]))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        result = await TreasuryYieldProvider(client, min_interval=0).risk_free_rate(date(2025, 2, 2))
    assert result["value"] == .045
    assert result["observation_date"] == "2025-01-31"
    assert [r.url.params["field_tdr_date_value_month"] for r in requests] == ["202502", "202501"]


@pytest.mark.asyncio
async def test_treasury_reuses_safe_transport_rejecting_redirects():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(302, headers={"Location": "https://private.invalid"}))) as client:
        with pytest.raises(ProviderError) as captured:
            await TreasuryYieldProvider(client, retries=0).risk_free_rate(date(2025, 1, 2))
    assert captured.value.code == "provider_http_error"
    assert "private" not in str(captured.value)


@pytest.mark.asyncio
async def test_fmp_history_beta_split_and_float_observations_retain_scope():
    def handle(request):
        assert request.url.params["apikey"] == "deterministic-test-key"
        path = request.url.path
        if path.endswith("profile"):
            return httpx.Response(200, json=[{"symbol": "MSFT", "beta": 1.2, "currency": "USD", "ipoDate": "1986-03-13"}])
        if path.endswith("full"):
            return httpx.Response(200, json=[{"symbol": "MSFT", "date": "2025-01-02", "close": 100}])
        if path.endswith("splits"):
            return httpx.Response(200, json=[{"symbol": "MSFT", "date": "2003-02-18", "numerator": 2, "denominator": 1}])
        return httpx.Response(200, json=[{"symbol": "MSFT", "date": "2025-01-02 10:00:00", "outstandingShares": 10, "source": "https://www.sec.gov/Archives/edgar/data/1/source.htm"}])
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        provider = FmpMarketDataProvider(client, "deterministic-test-key", min_interval=0)
        assert (await provider.profile("MSFT"))["beta"] == 1.2
        history = await provider.historical_prices("MSFT")
        assert history[0]["adjustment_basis"] == "split_adjusted"
        assert date.fromisoformat(history[0]["adjustment_date"])
        assert (await provider.splits("MSFT"))[0]["numerator"] == 2
        assert (await provider.share_float("MSFT"))["shares_outstanding"] == 10


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [{"date": "bad", "numerator": 2, "denominator": 1}, {"date": "2025-01-02", "numerator": 2, "denominator": 0}])
async def test_invalid_split_history_never_becomes_verified_no_events(bad):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[{"symbol": "MSFT", **bad}]))) as client:
        with pytest.raises(ProviderError) as captured:
            await FmpMarketDataProvider(client, "deterministic-test-key", min_interval=0).splits("MSFT")
    assert captured.value.code == "invalid_provider_response"


@pytest.mark.asyncio
@pytest.mark.parametrize("cik", [2, "bad", None])
async def test_sec_facts_reject_mismatched_or_invalid_reported_identity(cik):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"cik": cik, "facts": {}}))) as client:
        with pytest.raises(ProviderError) as captured:
            await SecEdgarProvider(client, "Offline Fixture contact@example.test", min_interval=.1).facts(1)
    assert captured.value.code == "incompatible_financial_identity"


def test_original_annual_eps_excludes_future_restatements():
    raw = raw_annual()
    for concept, value in [("EarningsPerShareDiluted", 20), ("NetIncomeLoss", 200)]:
        unit = next(iter(raw["facts"]["us-gaap"][concept]["units"]))
        original = deepcopy(raw["facts"]["us-gaap"][concept]["units"][unit][0])
        original.update(val=value, filed="2026-02-15", accn="0000000001-26-000001", fy=2025)
        raw["facts"]["us-gaap"][concept]["units"][unit].append(original)
    normalized = normalize_company_facts(raw, cik=1)
    assert normalized["annual"][0]["metrics"]["diluted_eps"] == 20
    native = original_annual_periods(raw, normalized, {"cik": "0000000001", "has_multiple_share_classes": False}, "2026-03-01")
    assert native[0]["metrics"]["diluted_eps"] == 10
    assert native[0]["publication_date"] == "2025-02-15"
    assert native[0]["eps_split_basis_verified"] is True
    assert all(obs["filed"] <= native[0]["publication_date"] for obs in native[0]["facts"]["diluted_eps"]["provenance"])


@pytest.mark.parametrize("multiple,income,verified", [(True, 100, False), (None, 100, False), (False, 200, False), (False, 100, True)])
def test_original_eps_split_basis_requires_class_and_common_earnings_reconciliation(multiple, income, verified):
    raw = raw_annual()
    raw["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"][0]["val"] = income
    normalized = normalize_company_facts(raw, cik=1)
    native = original_annual_periods(raw, normalized, {"cik": "0000000001", "has_multiple_share_classes": multiple}, "2025-02-16")
    assert native[0]["eps_split_basis_verified"] is verified


def test_cover_shares_remain_dated_and_distinct_from_weighted_shares():
    raw = raw_annual()
    raw["facts"]["dei"] = {"EntityCommonStockSharesOutstanding": annual_observation(12, unit="shares", start=None,
                                                                                      end="2025-02-10")}
    record = latest_sec_shares(raw, {"cik": "0000000001", "has_multiple_share_classes": False}, "2025-02-16")
    assert record["value"] == 12
    assert record["observation_date"] == "2025-02-10"
    assert record["scope_verified"] is True
    assert "not a live current-day" in record["warnings"][0]
    assert normalize_company_facts(raw)["annual"][0]["metrics"]["weighted_average_diluted_shares"] == 10


@pytest.mark.parametrize("value,unit,end,filed", [(0,"shares","2025-02-10","2025-02-15"), (10,"USD","2025-02-10","2025-02-15"),
                                               (10,"shares","2099-02-10","2099-02-15"), (10,"shares","2025-02-16","2025-02-15")])
def test_invalid_or_future_cover_shares_stay_unavailable(value, unit, end, filed):
    raw = raw_annual()
    raw["facts"]["dei"] = {"EntityCommonStockSharesOutstanding": annual_observation(value, unit=unit, start=None, end=end, filed=filed)}
    assert latest_sec_shares(raw, {"cik": "0000000001"}, "2025-02-16")["value"] is None


def test_multiple_classes_do_not_gain_automatic_current_shares_scope():
    raw = raw_annual()
    raw["facts"]["dei"] = {"EntityCommonStockSharesOutstanding": annual_observation(12, unit="shares", start=None, end="2025-02-10")}
    assert latest_sec_shares(raw, {"cik": "0000000001", "has_multiple_share_classes": True}, "2025-02-16")["scope_verified"] is False


def test_additional_mappings_preserve_verified_zero_and_nominal_preferred_scope():
    raw = raw_annual()
    concepts = raw["facts"]["us-gaap"]
    concepts["PreferredStockValueOutstanding"] = annual_observation(0, start=None)
    concepts["PreferredStockValue"] = annual_observation(25, start=None)
    concepts["MinorityInterest"] = annual_observation(15, start=None)
    concepts["InterestExpenseNonoperating"] = annual_observation(5)
    concepts["Depreciation"] = annual_observation(4)
    concepts["AmortizationOfIntangibleAssets"] = annual_observation(2)
    result = normalize_company_facts(raw)["annual"][0]["metrics"]
    assert result["preferred_stock_value_outstanding"] == 0
    assert result["preferred_stock_stated_value"] == 25
    assert result["minority_interest"] == 15
    assert result["interest_expense"] == 5
    assert result["depreciation_and_amortization"] is None  # component scopes are not assumed additive.
    assert result["total_debt"] is None


@pytest.mark.asyncio
async def test_per_result_cache_ttl_is_opt_in_positive_behavior_unchanged(session_factory):
    cache = CacheService(session_factory)
    now = utcnow()
    await cache.get_or_load("negative", 86400, "test", lambda: asyncio.sleep(0, result=CachedResult({"available": False}, "fresh", now, [], 300)))
    await cache.get_or_load("positive", 86400, "test", lambda: asyncio.sleep(0, result={"available": True}))
    negative, positive = cache._read("negative"), cache._read("positive")
    assert (negative.expires_at - negative.retrieved_at).total_seconds() == 300
    assert (positive.expires_at - positive.retrieved_at).total_seconds() == 86400


@pytest.mark.asyncio
async def test_optional_failure_cache_is_brief_and_preserves_stale_usable_evidence(session_factory):
    cache = CacheService(session_factory)
    service = AutomaticInputsService(SimpleNamespace(cache=cache), None, Settings(_env_file=None))
    calls = 0
    async def denied():
        nonlocal calls
        calls += 1
        raise ProviderError("provider_subscription_required", "Endpoint subscription restriction.", 503)
    first = await service._optional("denied", "test", denied)
    second = await service._optional("denied", "test", denied)
    assert first["status"] == second["status"] == "unavailable"
    assert calls == 1
    entry = cache._read("denied")
    assert (entry.expires_at - entry.retrieved_at).total_seconds() == 300
    cache._write("usable", {"available": True, "data": [{"value": 10}]}, 1, "test", utcnow() - timedelta(hours=1))
    stale = await service._optional("usable", "test", denied)
    assert stale["available"] is True and stale["status"] == "stale"
    assert stale["data"] == [{"value": 10}]
    assert cache._read("usable").payload["available"] is True


def test_erp_requires_complete_dated_policy_and_never_defaults_to_live_observation():
    default = AutomaticInputsService(SimpleNamespace(cache=None), None, Settings(_env_file=None))._erp()
    assert default["value"] is None
    settings = Settings(_env_file=None, valuation_erp_value=.05, valuation_erp_source="Independent research policy",
                        valuation_erp_publication_date=date(2025, 1, 1), valuation_erp_methodology="Explicit scenario estimate.")
    policy = AutomaticInputsService(SimpleNamespace(cache=None), None, settings)._erp()
    assert policy["value"] == .05
    assert policy["source_type"] == "policy"
    assert policy["kind"] == "policy"
    assert policy["publication_date"] == "2025-01-01"
