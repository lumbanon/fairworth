"""Source-owned quote-currency evidence; no venue-to-currency assumptions."""
from copy import deepcopy
from datetime import UTC, date, datetime
import hashlib
import json
import re

from app.providers.base import normalize_cik, ProviderError
from app.registry.listing_sources import exchange_mic

CONTRACT_VERSION = "quote-currency-1"
SOURCES = {"provider_quote": "https://financialmodelingprep.com/stable/quote",
           "provider_security_metadata": "https://financialmodelingprep.com/stable/profile"}


def _clock(value):
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
        return instant.astimezone(UTC) if isinstance(instant, datetime) and instant.tzinfo is not None and instant.utcoffset() is not None else None
    except (ValueError, TypeError, OverflowError):
        return None


def _currency(value):
    return value if isinstance(value, str) and re.fullmatch(r"[A-Z]{3}", value) else None


def _hash(record):
    try:
        return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    except (ValueError, TypeError):
        return None


def make_currency_evidence(row, identity, *, source_kind, retrieved_at):
    """Capture the exact relevant original fields after a permitted source read.

    The date is a metadata-snapshot version, not an invented effective listing
    date. This constructor never grants request or redistribution permission.
    """
    if source_kind not in SOURCES or not isinstance(row, dict):
        raise ValueError("Unsupported currency evidence source.")
    identity = identity or {}
    fields = ("symbol", "currency", "exchange", "cik") + (("price", "timestamp") if source_kind == "provider_quote" else ())
    original = {key: deepcopy(row[key]) for key in fields if key in row}
    retrieved = _clock(retrieved_at)
    return {"provider": "fmp", "source_kind": source_kind, "source_url": SOURCES[source_kind],
            "source_record_hash": _hash(original), "source_version_date": retrieved.date().isoformat() if retrieved else None,
            "retrieved_at": retrieved.isoformat() if retrieved else None,
            **{key: identity.get(key) for key in ("issuer_id", "instrument_id", "listing_id")},
            "provider_symbol": row.get("symbol"), "mic": identity.get("exchange_mic", identity.get("mic")),
            "currency": row.get("currency"), "original_record": original,
            "access_evidence": "source_response_after_caller_authorization",
            "display_license_status": "unresolved"}


def resolve_quote_currency(quote, identity=None, evidence_records=(), *, as_of=None, max_age_days=1):
    """Resolve only explicit original source currency for this exact security.

    Metadata is usable only as a recent dated source snapshot. It does not
    refresh listing/issuer proof, establish splits, or convert accounting units.
    """
    result, identity = deepcopy(quote), identity or {}
    if isinstance(max_age_days, bool) or not isinstance(max_age_days, int) or not 0 <= max_age_days <= 1:
        raise ValueError("Currency evidence requires the reviewed maximum one-day metadata age.")
    now = _clock(as_of) if as_of is not None else datetime.now(UTC)
    expected_symbol = (identity.get("provider_symbols") or {}).get("fmp") or identity.get("ticker") or quote.get("ticker")
    quote_day = _clock(quote.get("price_timestamp"))
    accepted, reasons = [], []
    own = quote.get("currency_evidence")
    expected_mic = identity.get("exchange_mic", identity.get("mic"))
    quote_scope_valid = quote.get("provider") == "fmp" and quote.get("ticker", quote.get("symbol")) == expected_symbol
    if expected_mic and exchange_mic(quote.get("exchange")) != expected_mic:
        quote_scope_valid = False
    if isinstance(own, dict) and isinstance(own.get("original_record"), dict):
        original_quote = own["original_record"]
        if original_quote.get("cik") is not None and identity.get("cik"):
            try:
                quote_scope_valid = quote_scope_valid and normalize_cik(original_quote["cik"]) == normalize_cik(identity["cik"])
            except ProviderError:
                quote_scope_valid = False
        if expected_mic and original_quote.get("exchange") and exchange_mic(original_quote["exchange"]) != expected_mic:
            quote_scope_valid = False
    if not quote_scope_valid:
        reasons.append("quote_source_security_scope_unverified")
    candidates = ([own] if isinstance(own, dict) else []) + list(evidence_records or ())
    for record in candidates:
        if not quote_scope_valid:
            continue
        if not isinstance(record, dict):
            reasons.append("invalid_currency_source_record")
            continue
        kind, original = record.get("source_kind"), record.get("original_record")
        retrieved = _clock(record.get("retrieved_at"))
        try:
            version = date.fromisoformat(record.get("source_version_date", ""))
        except (ValueError, TypeError):
            version = None
        value = _currency(record.get("currency"))
        if (kind not in SOURCES or record.get("provider") != "fmp" or record.get("source_url") != SOURCES.get(kind)
                or not isinstance(original, dict) or not re.fullmatch(r"[0-9a-f]{64}", str(record.get("source_record_hash", "")))
                or record.get("source_record_hash") != _hash(original)
                or value is None or original.get("currency") != value or original.get("symbol") != expected_symbol
                or record.get("provider_symbol") != expected_symbol):
            reasons.append("currency_source_or_symbol_unverified")
            continue
        if (now is None or retrieved is None or version is None or retrieved > now or version > retrieved.date()
                or (now.date() - version).days > max_age_days or (now - retrieved).total_seconds() > max_age_days * 86400):
            reasons.append("currency_source_expired_or_future")
            continue
        if any(identity.get(key) is not None and record.get(key) != identity[key] for key in ("issuer_id", "instrument_id", "listing_id")):
            reasons.append("currency_security_identity_mismatch")
            continue
        if kind == "provider_quote":
            if (record is not own or value != _currency(quote.get("currency"))
                    or original.get("price") != quote.get("price")):
                reasons.append("currency_quote_binding_mismatch")
                continue
            if expected_mic and exchange_mic(original.get("exchange")) != expected_mic:
                reasons.append("currency_venue_mismatch")
                continue
            timestamp = original.get("timestamp")
            try:
                observed = datetime.fromtimestamp(timestamp, UTC) if not isinstance(timestamp, bool) else None
            except (ValueError, TypeError, OverflowError, OSError):
                observed = None
            if observed != quote_day:
                reasons.append("currency_quote_binding_mismatch")
                continue
        else:
            if not all(identity.get(key) and record.get(key) == identity[key] for key in ("issuer_id", "instrument_id", "listing_id")):
                reasons.append("currency_listing_scope_unverified")
                continue
            mic = identity.get("exchange_mic", identity.get("mic"))
            if (not mic or record.get("mic") != mic or exchange_mic(original.get("exchange")) != mic
                    or quote.get("exchange") and exchange_mic(quote["exchange"]) != mic):
                reasons.append("currency_venue_mismatch")
                continue
            try:
                cik_matches = normalize_cik(original.get("cik")) == normalize_cik(identity.get("cik"))
            except ProviderError:
                cik_matches = False
            if not cik_matches or quote_day is None or version > quote_day.date():
                reasons.append("currency_issuer_or_observation_scope_unverified")
                continue
        accepted.append(deepcopy(record))
    values = {record["currency"] for record in accepted}
    # A contradictory explicit quote unit must not be overwritten by metadata.
    explicit = _currency(quote.get("currency"))
    if explicit is not None and values and explicit not in values:
        values.add(explicit)
    status = "conflict" if len(values) > 1 else "verified" if len(values) == 1 else "quote_currency_unverified"
    currency = next(iter(values)) if status == "verified" else None
    result["original_currency"] = quote.get("original_currency", quote.get("currency"))
    result["currency"] = currency
    result["currency_resolution"] = {"methodology_version": CONTRACT_VERSION, "status": status, "currency": currency,
        "reason_codes": (["conflicting_currency_evidence"] if status == "conflict" else [] if status == "verified" else list(dict.fromkeys(reasons + ["quote_currency_unverified"]))),
        "evidence": accepted,
        "limitations": ["Currency evidence does not verify listing ownership, financial reporting currency, or corporate-action compatibility."]}
    return result
