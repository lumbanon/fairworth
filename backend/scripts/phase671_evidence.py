"""Validate a locally retained Phase 6.7.1 acquisition receipt, without I/O online.

This inventory is not an authorization system or a financial-input adapter.
The caller must verify actual user consent independently. Valid source bytes do
not establish current listing, share compatibility or valuation eligibility.
"""
from datetime import UTC, date, datetime
import hashlib
import json
import math
from pathlib import Path
import re

from app.registry.importers import sec_reference_records
from app.registry.listing_sources import SOURCES, parse_nasdaq_directory


CONTRACT_VERSION = "phase671-local-evidence-1"
SYMBOLS = {"AAPL": "0000320193", "MSFT": "0000789019", "NVDA": "0001045810",
           "AMZN": "0001018724", "PGR": "0000080661"}
SEC_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
FMP_ORIGIN = "https://financialmodelingprep.com/stable/"
_TOP_FIELDS = {"schema_version", "authorization", "authorization_question_id", "started_at", "limits",
               "requests", "complete", "finished_at", "actual_requests", "actual_bytes", "stopped_providers"}
_RECORD_FIELDS = {"provider", "endpoint", "url", "symbol", "cik", "byte_limit", "started_at", "status",
                  "http_status", "error_type", "retrieved_at", "bytes", "sha256", "file"}
_STATUSES = {"received", "http_error", "provider_error", "invalid_json", "transport_error", "size_limit_exceeded"}
_DENIALS = {401, 402, 403, 429}


def _fail(reason):
    # Never interpolate raw provider payloads, paths, URLs or credentials.
    raise ValueError("Invalid local Phase 6.7.1 evidence: " + reason + ".")


def _json(content):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                _fail("duplicate JSON field")
            result[key] = value
        return result
    try:
        return json.loads(content, object_pairs_hook=unique,
                          parse_constant=lambda _: _fail("nonfinite JSON number"))
    except (UnicodeError, json.JSONDecodeError):
        _fail("unreadable JSON")


def _clock(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
        if not isinstance(parsed, datetime) or parsed.tzinfo is None or parsed.utcoffset() is None:
            _fail("a timezone-aware clock is required")
        return parsed.astimezone(UTC)
    except (ValueError, TypeError, AttributeError):
        _fail("a timezone-aware clock is required")


def _integer(value, minimum, maximum):
    return not isinstance(value, bool) and isinstance(value, int) and minimum <= value <= maximum


def _safe_metadata(value):
    if isinstance(value, dict):
        for key, item in value.items():
            compact = re.sub(r"[^a-z]", "", str(key).lower())
            if any(term in compact for term in ("apikey", "password", "secret", "credential", "authorizationheader", "useragent", "contact", "email")):
                _fail("private metadata field")
            _safe_metadata(item)
    elif isinstance(value, list):
        for item in value:
            _safe_metadata(item)
    elif isinstance(value, str):
        if (re.search(r"(?i)(apikey|api_key|password|secret|bearer)\s*[=:]", value)
                or re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", value)):
            _fail("private metadata content")


def _request_contract(record):
    provider, endpoint, symbol = (record.get(key) for key in ("provider", "endpoint", "symbol"))
    if provider == "nasdaq" and endpoint in SOURCES and symbol is None and record.get("cik") is None:
        expected, cap = SOURCES[endpoint], 5_000_000
    elif provider == "sec" and endpoint == "company_tickers_exchange" and symbol is None and record.get("cik") is None:
        expected, cap = SEC_URL, 5_000_000
    elif (provider == "fmp" and symbol in SYMBOLS and record.get("cik") == SYMBOLS[symbol]
          and (endpoint in {"quote", "profile", "splits"}
               or endpoint == "historical-price-eod/full" and symbol in {"AMZN", "PGR"})):
        expected = FMP_ORIGIN + endpoint
        cap = 5_000_000 if endpoint == "historical-price-eod/full" else 1_000_000
    else:
        _fail("request is outside the exact approved inventory")
    if record.get("url") != expected or record.get("byte_limit") != cap:
        _fail("endpoint or response budget mismatch")
    return provider, endpoint, symbol, cap


def _market_payload(payload, record, retrieved):
    if not isinstance(payload, list) or len(payload) > 100_000 or not all(isinstance(row, dict) for row in payload):
        _fail("unexpected market source shape")
    symbol, endpoint = record["symbol"], record["endpoint"]
    def positive(value):
        return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and value > 0
    for row in payload:
        if (row.get("symbol", symbol if endpoint == "splits" else None) != symbol
                or row.get("cik") is not None and str(row["cik"]).zfill(10) != SYMBOLS[symbol]):
            _fail("market response security identity mismatch")
        if endpoint == "quote" and (not positive(row.get("price")) or row.get("timestamp") is None):
            _fail("a quote requires a finite price and original observation clock")
        if endpoint == "profile" and (not re.fullmatch(r"[A-Z]{3}", str(row.get("currency", "")))
                                      or not isinstance(row.get("exchange"), str) or not row["exchange"]):
            _fail("a profile requires its original currency and exchange")
        if endpoint == "splits" and (not positive(row.get("numerator")) or not positive(row.get("denominator"))):
            _fail("a split requires positive reported factors")
        if endpoint == "historical-price-eod/full" and not positive(row.get("close")):
            _fail("historical market data requires a finite reported close")
        if endpoint == "quote" and row.get("timestamp") is not None:
            timestamp = row["timestamp"]
            if (isinstance(timestamp, bool) or not isinstance(timestamp, (int, float))
                    or not math.isfinite(timestamp)):
                _fail("invalid quote observation clock")
            try:
                observed = datetime.fromtimestamp(timestamp, UTC)
            except (ValueError, OverflowError, OSError):
                _fail("invalid quote observation clock")
            if observed > retrieved:
                _fail("future quote observation")
        if endpoint in {"splits", "historical-price-eod/full"}:
            try:
                observed = date.fromisoformat(row.get("date", ""))
            except (TypeError, ValueError):
                _fail("invalid market observation date")
            if observed > retrieved.date():
                _fail("future market observation")
    return {"record_count": len(payload), "security_scope": "request_and_response_symbol" if endpoint != "splits" else "request_symbol_and_any_returned_symbol",
            "empty_response_is_not_verified_absence": True}


def load_local_evidence_manifest(path, *, audit_clock, allowed_root=None,
                                 expected_authorization_question_id=None):
    """Return verified source inventory and raw bytes for isolated offline replay.

    No HTTP client, provider loader, settings, API key, or database is used. The
    receipt is caller supplied; matching its ID is not independent proof of
    consent. ``payload`` fields must stay in local audit memory/ignored storage.
    """
    path = Path(path).resolve()
    root = Path(allowed_root).resolve() if allowed_root is not None else path.parent
    try:
        path.relative_to(root)
    except ValueError:
        _fail("manifest is outside the allowed local directory")
    if not path.is_file() or path.stat().st_size > 200_000:
        _fail("missing or oversized manifest")
    manifest = _json(path.read_bytes())
    if (not isinstance(manifest, dict) or set(manifest) - _TOP_FIELDS
            or manifest.get("schema_version") != "phase671-acquisition-1"
            or manifest.get("complete") is not True):
        _fail("unsupported or incomplete receipt")
    _safe_metadata(manifest)
    receipt = manifest.get("authorization_question_id")
    if (not isinstance(receipt, str) or not re.fullmatch(r"call_[A-Za-z0-9_-]{8,100}", receipt)
            or expected_authorization_question_id is not None and receipt != expected_authorization_question_id
            or not isinstance(manifest.get("authorization"), str) or not manifest["authorization"].strip()):
        _fail("missing or mismatched caller authorization receipt")
    limits = manifest.get("limits")
    if limits != {"requests": 20, "bytes": 40_000_000, "timeout_seconds": 30,
                  "retries": 0, "redirects": False, "concurrency": 1}:
        _fail("acquisition limits differ from the bounded contract")
    now, started, finished = (_clock(value) for value in (audit_clock, manifest.get("started_at"), manifest.get("finished_at")))
    if not started <= finished <= now:
        _fail("future or inverted acquisition clocks")
    requests = manifest.get("requests")
    if not isinstance(requests, list) or not 1 <= len(requests) <= 20:
        _fail("request count exceeds the bounded contract")
    inventory, seen, stopped, previous, total = [], set(), set(), None, 0
    for record in requests:
        if not isinstance(record, dict) or set(record) - _RECORD_FIELDS:
            _fail("unexpected request metadata")
        provider, endpoint, symbol, cap = _request_contract(record)
        identity = provider, endpoint, symbol
        if identity in seen or provider in stopped:
            _fail("duplicate request or a request after provider denial")
        seen.add(identity)
        begin, end = _clock(record.get("started_at")), _clock(record.get("retrieved_at"))
        if not started <= begin <= end <= finished or previous is not None and (begin - previous).total_seconds() < 1:
            _fail("request clocks violate sequence or minimum interval")
        previous = end
        status, code = record.get("status"), record.get("http_status")
        if status not in _STATUSES or code is not None and not _integer(code, 100, 599):
            _fail("invalid provider outcome")
        if status in {"received", "provider_error", "invalid_json"} and code != 200 or status == "http_error" and (code is None or code == 200):
            _fail("inconsistent HTTP outcome")
        if not _integer(record.get("bytes"), 0, cap):
            _fail("response exceeds its byte budget")
        total += record["bytes"]
        if total > 40_000_000 or not re.fullmatch(r"[0-9a-f]{64}", str(record.get("sha256", ""))):
            _fail("total byte budget or source hash is invalid")
        name = record.get("file")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+\.raw", name):
            _fail("unsafe source path")
        source = (path.parent / name).resolve()
        try:
            source.relative_to(root)
            source.relative_to(path.parent)
        except ValueError:
            _fail("source file escapes the allowed directory")
        if not source.is_file() or source.stat().st_size != record["bytes"]:
            _fail("source size does not match its receipt")
        content = source.read_bytes()
        if hashlib.sha256(content).hexdigest() != record["sha256"]:
            _fail("source hash does not match its receipt")
        payload, source_summary = None, {"status": "unavailable_provider_response"}
        if status == "received":
            if provider == "nasdaq":
                payload = parse_nasdaq_directory(content, endpoint, retrieved_at=record["retrieved_at"])
                if date.fromisoformat(payload["provenance"]["as_of"]) > end.date():
                    _fail("future listing publication date")
                source_summary = {"record_count": len(payload["records"]), "status": "parsed_listing_observations"}
            else:
                payload = _json(content)
                if provider == "sec":
                    if (not isinstance(payload, dict) or set(payload) != {"fields", "data"}
                            or payload["fields"] != ["cik", "name", "ticker", "exchange"]
                            or not isinstance(payload["data"], list) or len(payload["data"]) > 100_000
                            or any(not isinstance(row, list) or len(row) != 4 for row in payload["data"])):
                        _fail("unexpected SEC directory shape")
                    source_summary = {"record_count": len(sec_reference_records(payload)), "status": "parsed_issuer_reference_only"}
                else:
                    source_summary = {**_market_payload(payload, record, end), "status": "validated_raw_market_inventory"}
        if code in _DENIALS or status in {"provider_error", "invalid_json", "transport_error", "size_limit_exceeded"}:
            stopped.add(provider)
        inventory.append({**record, "source_summary": source_summary, "payload": payload})
    if (manifest.get("actual_requests") != len(requests) or manifest.get("actual_bytes") != total
            or set(manifest.get("stopped_providers", [])) != stopped):
        _fail("final receipt totals or provider stop states disagree")
    return {"contract_version": CONTRACT_VERSION, "audit_clock": now.isoformat(),
        "authorization": {"question_id": receipt, "verification": "caller_supplied_receipt_not_independent_consent"},
        "actual_requests": len(requests), "actual_bytes": total, "inventory": inventory,
        "limitations": ["The caller must independently verify actual explicit authorization; a manifest cannot grant consent.",
            "Validated bytes and request scope do not verify financial facts, current listing, compatible share basis, licensing, or valuation eligibility.",
            "Source publication, observation and retrieval clocks remain separate; no proof freshness is extended.",
            "No HTTP request, production cache write, or database import is performed."]}
