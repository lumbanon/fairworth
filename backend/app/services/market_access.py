"""Explicit free-plan request scope, bounded reservations and retained denials.

Called inside existing data-cache loaders: valid caches require no reservation;
stale-on-error behavior preserves original observations. No fallback provider,
account upgrade, endpoint discovery, or request retry is performed here.
"""
import asyncio
from datetime import timedelta
import hashlib
import json
from uuid import uuid4

from app.core.database import utcnow
from app.providers.base import ProviderError
from app.providers.market_data import FmpMarketDataProvider
from app.services.security_identity import market_call
from app.services.security_identity import cache_scope

ENDPOINTS = {"quote": "quote", "profile": "profile", "historical_prices": "historical-price-eod/full",
             "dividends": "dividends", "splits": "splits", "share_float": "shares-float"}
DENIALS = {"provider_subscription_required", "provider_authentication_failed", "provider_access_denied", "provider_not_authorized"}


def _scope(market, method, identity, args):
    endpoint = ENDPOINTS.get(method)
    if method == "financial_statements":
        endpoint = "balance-sheet-statement" if args and args[0] == "balance_sheet" else "cash-flow-statement"
    symbol = market._symbol(identity["ticker"], identity)
    exact = {key: identity.get(key) for key in ("issuer_id", "instrument_id", "listing_id", "cik")}
    return endpoint, symbol, {**exact, "symbol": symbol, "endpoint": endpoint}


def _restriction_key(exact, settings):
    raw = json.dumps({**exact, "review": getattr(settings, "fmp_access_review_id", "initial")}, sort_keys=True)
    return "market:fmp:access:v1:" + hashlib.sha256(raw.encode()).hexdigest()


def capability_snapshot(market, cache, settings, identity):
    if not hasattr(market, "capability_snapshot"):
        return {"provider": market.name, "display_license_status": "unresolved", "endpoints": {}}
    result = market.capability_snapshot(identity["ticker"], identity)
    # A retained successful response is dated access evidence. Preserve that
    # diagnostic across worker restarts without treating it as current access.
    cached = cache._read(f"market:{market.name}:quote:{cache_scope(identity)}")
    prior = cached.payload.get("provider_capabilities", {}) if cached and isinstance(cached.payload, dict) else {}
    prior = prior if isinstance(prior, dict) else {}
    if prior.get("scope") == result.get("scope"):
        for endpoint, record in result.get("endpoints", {}).items():
            old = prior.get("endpoints", {}).get(endpoint, {})
            if record.get("evidence_kind") == "none" and old.get("observed_at") and old.get("access_status") == "observed_access":
                result["endpoints"][endpoint] = {**old, "evidence_kind": "cached_dated_request_outcome"}
    for method in ENDPOINTS:
        endpoint, symbol, exact = _scope(market, method, identity, ())
        entry = result.get("endpoints", {}).get(endpoint)
        if not isinstance(entry, dict):
            continue
        entry["acquisition_authorized"] = endpoint in getattr(settings, "fmp_authorized_endpoints", {}).get(symbol, [])
        persisted = cache._read(_restriction_key(exact, settings))
        if persisted and isinstance(persisted.payload, dict):
            entry.update(access_status="requires_paid_subscription" if persisted.payload.get("error_code") == "provider_subscription_required" else "explicitly_denied",
                         error_code=persisted.payload.get("error_code"), observed_at=persisted.payload.get("observed_at"),
                         evidence_kind="retained_request_denial")
    result["request_budget"] = {"daily_ceiling": getattr(settings, "fmp_daily_request_budget", 50),
        "scope": "Rolling 24 hours in this Fairworth database only; usage by other clients is not known."}
    return result


async def market_access_call(market, cache, settings, method, identity, *args):
    # Injected offline providers retain their existing interface. The actual FMP
    # adapter always passes this guard in application service loaders.
    if not isinstance(market, FmpMarketDataProvider):
        return await market_call(market, method, identity, *args)
    endpoint, symbol, exact = _scope(market, method, identity, args)
    if not endpoint or endpoint not in getattr(settings, "fmp_authorized_endpoints", {}).get(symbol, []):
        raise ProviderError("market_request_not_authorized", "This market-data endpoint is outside the explicitly configured acquisition scope; cached evidence remains available.", 403)
    restriction = _restriction_key(exact, settings)
    previous = cache._read(restriction)
    if previous and isinstance(previous.payload, dict) and previous.payload.get("error_code") in DENIALS:
        raise ProviderError(previous.payload["error_code"], "A retained endpoint/security access denial requires an explicit entitlement review; no automatic request was made.", 503)
    # Coordination uses the existing atomic database lease. No SQL transaction
    # or lease spans the network operation. Failed/cancelled requests consume
    # their reservations conservatively, rather than granting extra attempts.
    lock, owner = "market:fmp:free-request-budget:v2", str(uuid4())
    if not cache._acquire_lease(lock, owner):
        raise ProviderError("market_request_budget_busy", "The shared provider request budget is being reserved; no additional request was made.", 503)
    try:
        now = utcnow()
        key = lock + ":rolling-24h"
        ledger = cache._read(key)
        record = ledger.payload if ledger and isinstance(ledger.payload, dict) else {}
        from app.repositories.financial_repository import parse_instant
        saved = record.get("reservations", [])
        if not isinstance(saved, list) or len(saved) > 250:
            raise ProviderError("market_request_budget_unverified", "The shared request budget needs review; no request was made.", 503)
        reservations = [parse_instant(item) for item in saved]
        if any(item is None for item in reservations):
            raise ProviderError("market_request_budget_unverified", "The shared request budget needs review; no request was made.", 503)
        reservations = [item for item in reservations if item > now - timedelta(days=1)]
        count = len(reservations)
        maximum = getattr(settings, "fmp_daily_request_budget", 50)
        if not isinstance(count, int) or isinstance(count, bool) or not 0 <= count < maximum:
            raise ProviderError("market_request_budget_exhausted", "The configured daily provider request budget is exhausted; no additional request was made.", 429)
        scheduled = parse_instant(record.get("next_request_at"))
        start = max(now, scheduled) if scheduled else now
        interval = getattr(settings, "fmp_minimum_request_interval_seconds", 1)
        cache._write(key, {"reservations": [item.isoformat() for item in reservations] + [start.isoformat()], "next_request_at": (start + timedelta(seconds=interval)).isoformat()},
                     172800, "fairworth-market-request-budget")
    finally:
        cache._release_lease(lock, owner)
    if start > now:
        await asyncio.sleep((start - now).total_seconds())
    # Another worker may have received a denial while this reservation waited.
    # Keep the reservation consumed, but suppress the now-disallowed request.
    previous = cache._read(restriction)
    if previous and isinstance(previous.payload, dict) and previous.payload.get("error_code") in DENIALS:
        raise ProviderError(previous.payload["error_code"], "A concurrent access denial was retained before dispatch; no further request was made.", 503)
    try:
        return await market_call(market, method, identity, *args)
    except ProviderError as error:
        if error.code in DENIALS:
            cache._write(restriction, {"error_code": error.code, "observed_at": utcnow().isoformat(),
                "scope": exact, "retry_policy": "manual_entitlement_review_required"}, 315360000, "fairworth-market-access")
        raise
