"""Dated endpoint access evidence, independent of permission and display rights."""
from copy import deepcopy

ENDPOINTS = ("quote", "profile", "historical-price-eod/full", "dividends", "splits",
             "shares-float", "balance-sheet-statement", "cash-flow-statement")
ERROR_STATES = {"provider_subscription_required": "requires_paid_subscription",
                "provider_access_denied": "explicitly_denied", "provider_authentication_failed": "explicitly_denied",
                "provider_rate_limited": "rate_limited", "not_found": "unsupported_source_field"}


def capability_record(endpoint, *, observed_at=None, error_code=None, success=False):
    return {"endpoint": endpoint, "access_status": "observed_access" if success else
            ERROR_STATES.get(error_code, "temporarily_unavailable" if error_code else "not_yet_tested"),
            "observed_at": observed_at, "error_code": error_code,
            "evidence_kind": "dated_request_outcome" if observed_at else "none",
            "display_license_status": "unresolved",
            "entitlement_scope": "Exact endpoint and selected security; a past successful request is not a current entitlement guarantee."}


def capability_snapshot(records, scope):
    return {"methodology_version": "provider-capabilities-1", "provider": "fmp", "subscription": "free",
            "scope": deepcopy({key: scope.get(key) for key in ("ticker", "issuer_id", "instrument_id", "listing_id")}),
            "display_license_status": "unresolved",
            "endpoints": {endpoint: deepcopy(records.get(endpoint, capability_record(endpoint))) for endpoint in ENDPOINTS},
            "limits": {"documented_calls_per_day": 250, "documented_trailing_30_day_bandwidth_bytes": 500_000_000,
                       "remaining_account_allowance": None},
            "limitations": ["Configured credentials and endpoint documentation do not establish entitlement.",
                            "Operator authorization, source freshness and licensing are checked separately."]}
