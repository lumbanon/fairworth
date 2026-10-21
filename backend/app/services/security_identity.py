"""Stable security scope and conservative compatibility checks; no fetching."""
from copy import deepcopy
import hashlib
import json
from datetime import date

from app.core.exceptions import ApiError
from app.providers.base import normalize_cik, ProviderError

IDENTITY_FIELDS = ("issuer_id", "instrument_id", "listing_id", "ticker", "display_symbol", "security_description", "source_security_identifier", "cik", "exchange", "exchange_mic",
                   "instrument_type", "listing_status", "identity_status", "share_class", "aliases", "symbol_aliases",
                   "source_refs", "classification_evidence", "provider_symbols", "adr_metadata", "adr_ratio", "adr_ratio_verified",
                   "security_form", "issuer_business_category", "issuer_classification_evidence", "listing_verification", "issuer_linkage",
                   "share_basis_verified", "reporting_currency", "quote_currency", "filing_regime", "valid_from", "valid_to", "symbol_reassigned",
                   "registry_as_of", "registry_retrieved_at", "registry_version", "registry_status", "registry_warnings",
                   "verification_state", "proof_expiry")
ORDINARY_TYPES = {"common_stock", "domestic_common_stock", "foreign_ordinary", "foreign_ordinary_share",
                  "adr", "ads", "reit", "financial_institution", "insurance"}
UNSUPPORTED_TYPES = {"etf", "closed_end_fund", "fund", "preferred", "preferred_stock", "warrant", "rights", "right", "unit", "other"}


def security_identity(company):
    return {key: deepcopy(company[key]) for key in IDENTITY_FIELDS if key in company}


def scope_kwargs(instrument_id=None, listing_id=None):
    """Do not add optional arguments to legacy injected provider/service calls."""
    return {key: value for key, value in (("instrument_id", instrument_id), ("listing_id", listing_id)) if value is not None}


def cache_scope(company):
    """Legacy fixtures retain their keys; identified instruments never read them."""
    if not company.get("instrument_id"):
        return company["ticker"]
    parts = {key: company.get(key) for key in ("issuer_id", "instrument_id", "listing_id", "cik", "ticker", "exchange_mic",
                                             "valid_from", "valid_to", "provider_symbols", "instrument_type", "identity_status",
                                             "listing_status", "adr_metadata", "symbol_reassigned", "share_class", "symbol_aliases",
                                             "security_form", "issuer_business_category", "issuer_classification_evidence", "listing_verification", "filing_regime",
                                             "verification_state", "proof_expiry")}
    parts = {key: None if value in ({}, []) else value for key, value in parts.items()}
    parts["symbol_reassigned"] = bool(parts["symbol_reassigned"])
    return "security-v2:" + hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:40]


def within_listing_period(company, observation):
    if not company.get("instrument_id"):
        return True
    if company.get("symbol_reassigned") and not company.get("valid_from"):
        return False
    start, end = company.get("valid_from"), company.get("valid_to")
    if not start and not end:
        return True
    try:
        observed = date.fromisoformat(str(observation)[:10])
        return (not start or observed >= date.fromisoformat(str(start)[:10])) and (not end or observed <= date.fromisoformat(str(end)[:10]))
    except (TypeError, ValueError):
        return False


def same_identity(left, right):
    if left.get("cik") != right.get("cik"):
        return False
    for field in ("issuer_id", "instrument_id", "listing_id"):
        if (left.get(field) is not None or right.get(field) is not None) and left.get(field) != right.get(field):
            return False
    return True


def applicability(company):
    """Hard gates cannot be replaced with valuation assumption overrides."""
    if not company.get("instrument_id"):
        return None  # Existing canonical financial fixtures remain compatible.
    verification = company.get("listing_verification") or {}
    if company.get("identity_status") in {"ambiguous", "conflicting", "unresolved"} or verification.get("status") == "conflicting":
        return "identity_ambiguous", "The selected security identity is ambiguous."
    if company.get("listing_status") in {"inactive", "delisted", "suspended"}:
        return "inactive_listing", "The selected listing is inactive or suspended; current ordinary-stock valuation is unavailable."
    kind = company.get("security_form", company.get("instrument_type"))
    if kind in UNSUPPORTED_TYPES:
        return "unsupported_instrument_type", "Ordinary-stock valuation does not apply to this instrument type."
    if kind not in ORDINARY_TYPES:
        return "instrument_classification_unverified", "The instrument classification has not been verified."
    if company.get("identity_status") != "verified":
        return "security_identity_unverified", "A verified issuer and listed instrument identity is required for valuation."
    if company.get("listing_status") != "active" or verification and verification.get("status") != "verified":
        return "listing_status_unverified", "The active listing status of this instrument has not been verified."
    if verification and (verification.get("stale") is True or company.get("registry_status") in {"stale", "partial"}):
        return "stale_listing_verification", "The retained listing observation does not establish current listing status; a fresh, valid authoritative observation is required for a current scoped valuation."
    if kind in {"adr", "ads"}:
        metadata = company.get("adr_metadata") or {}
        ratio = company.get("adr_ratio", metadata.get("ratio"))
        if (not company.get("adr_ratio_verified", metadata.get("ratio_verified")) or not isinstance(ratio, (int, float))
                or isinstance(ratio, bool) or not 0 < ratio < float("inf")
                or company.get("share_basis_verified", metadata.get("share_basis_verified")) is not True):
            return "adr_share_basis_unverified", "A sourced ADR ratio and compatible per-depositary-security share basis are required."
        if ratio != 1:
            return "adr_per_security_conversion_unsupported", "The reported issuer amounts require an ADR conversion that this valuation engine does not implement; underlying shares are not treated as depositary securities."
    if kind in {"foreign_ordinary", "foreign_ordinary_share", "adr", "ads"} or company.get("filing_regime") in {"foreign_private_issuer", "20-F", "40-F"}:
        metadata = company.get("adr_metadata") or {}
        if company.get("share_basis_verified", metadata.get("share_basis_verified")) is not True:
            return "foreign_share_basis_unverified", "The listed security and underlying issuer share basis have not been reconciled."
        reporting = company.get("reporting_currency", metadata.get("reporting_currency"))
        quote = company.get("quote_currency", metadata.get("quote_currency"))
        if not reporting or not quote or reporting != quote:
            return "foreign_currency_basis_unverified", "Reporting and quote currencies require verified compatibility; no conversion is inferred."
    return None


def check_provider_identity(company, payload):
    if not company.get("instrument_id"):
        return
    expected, actual = company.get("cik"), payload.get("cik")
    if expected and actual:
        try:
            valid = normalize_cik(expected) == normalize_cik(actual)
        except ProviderError:
            valid = False
        if not valid:
            raise ApiError("incompatible_financial_identity", "Provider issuer identity does not match the selected security.", 502)
    symbol = payload.get("ticker", payload.get("symbol"))
    aliases = company.get("symbol_aliases", [])
    permitted = {company["ticker"]}
    symbols = company.get("provider_symbols") or {}
    for value in symbols.values() if isinstance(symbols, dict) else []:
        if isinstance(value, str):
            permitted.add(value)
    for alias in aliases:
        value = alias.get("symbol", alias.get("alias")) if isinstance(alias, dict) else alias
        if isinstance(value, str):
            permitted.add(value)
    if symbol and symbol not in permitted:
        raise ApiError("incompatible_security_identity", "Provider symbol does not match a verified alias of the selected security.", 502)
    def venue(value):
        value = str(value or "").upper()
        return {"XNAS": "NASDAQ", "NASDAQ GLOBAL SELECT": "NASDAQ", "NASDAQ GLOBAL SELECT MARKET": "NASDAQ",
                "NASDAQ GLOBAL MARKET": "NASDAQ", "NASDAQ CAPITAL MARKET": "NASDAQ", "NASDAQ STOCK MARKET": "NASDAQ",
                "XNYS": "NYSE", "NEW YORK STOCK EXCHANGE": "NYSE", "XASE": "AMEX", "NYSE AMERICAN": "AMEX"}.get(value, value)
    expected_venue, actual_venue = company.get("exchange"), payload.get("exchange")
    if expected_venue and actual_venue and venue(expected_venue) != venue(actual_venue):
        raise ApiError("incompatible_security_identity", "Provider exchange does not match the selected listing.", 502)
    if payload.get("share_class") and company.get("share_class") and payload["share_class"] != company["share_class"]:
        raise ApiError("incompatible_security_identity", "Provider share class does not match the selected security.", 502)
    kind = company.get("security_form", company.get("instrument_type"))
    if (payload.get("isEtf") is True and kind != "etf"
            or payload.get("isFund") is True and kind not in {"etf", "fund", "closed_end_fund"}
            or payload.get("isAdr") is True and kind not in {"adr", "ads"}):
        raise ApiError("incompatible_security_identity", "Provider instrument classification conflicts with the selected security.", 502)


async def market_call(provider, method, company, *args):
    kwargs = {"identity": company} if getattr(provider, "supports_security_identity", False) else {}
    result = await getattr(provider, method)(company["ticker"], *args, **kwargs)
    if isinstance(result, dict):
        check_provider_identity(company, result)
        if method == "quote" and not within_listing_period({**company, "symbol_reassigned": False}, result.get("price_timestamp")):
            raise ApiError("incompatible_security_identity", "The quote observation falls outside the verified listing period.", 502)
    elif isinstance(result, list) and method in {"historical_prices", "splits", "dividends"}:
        if company.get("symbol_reassigned") and not company.get("valid_from"):
            raise ProviderError("historical_security_scope_unverified", "A reused symbol requires a verified listing start date before historical provider observations can be assigned.", 422)
        result = [row for row in result if within_listing_period(company, row.get("date"))]
    return result
