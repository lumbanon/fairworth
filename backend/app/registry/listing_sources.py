"""Bounded offline Nasdaq Trader parsers. This module never downloads data.

Directory membership is a dated listing observation, not a promise of trading,
an IPO date, a permanent identifier, issuer CIK, or a compatible share basis.
"""
from datetime import datetime
import csv
import hashlib
import io
import json
import re

from app.providers.base import ProviderError, validate_ticker

PARSER_VERSION = "nasdaq-directory-1"
SOURCES = {
    "nasdaqlisted": "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
    "otherlisted": "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
}
EXCHANGES = {"N": ("NYSE", "XNYS"), "A": ("NYSE American", "XASE"),
             "P": ("NYSE Arca", "ARCX"), "Z": ("Cboe BZX", "BATS"), "V": ("IEX", "IEXG")}
US_MICS = {"XNAS", "XNYS", "XASE", "ARCX", "BATS", "IEXG"}


def exchange_mic(exchange, mic=None):
    if mic:
        return str(mic).upper()
    text = str(exchange or "").strip().upper()
    return {"NASDAQ": "XNAS", "NASDAQ GLOBAL SELECT": "XNAS", "NASDAQ GLOBAL MARKET": "XNAS",
            "NASDAQ CAPITAL MARKET": "XNAS", "NYSE": "XNYS", "NEW YORK STOCK EXCHANGE": "XNYS",
            "NYSE AMERICAN": "XASE", "NYSE MKT": "XASE", "AMEX": "XASE", "NYSE ARCA": "ARCX",
            "CBOE BZX": "BATS", "BATS": "BATS", "IEX": "IEXG"}.get(text)


def security_form(description, etf):
    """Only explicit description/ETF evidence, never ticker suffix inference."""
    # Nasdaq normally separates the issuer name from the security description.
    # Do not classify an issuer called "Rights ..." from that name alone.
    text = description.rsplit(" - ", 1)[-1].casefold()
    if etf == "Y":
        return "etf"
    unit = re.search(r"\bunits?\b", text)
    ordinary = re.search(r"\b(common stock|common shares?|ordinary shares?|preferred|warrants?)\b", text)
    if unit and (ordinary is None or unit.start() < ordinary.start()) and not re.search(r"\b(american depositary|american depository|adrs?|adss?)\b", text[:unit.start()]):
        return "unit"  # A composite unit must not inherit a component's form.
    right = re.search(r"\brights?\b", text)
    if right and ordinary and right.start() < ordinary.start() and re.search(r"\brights?\s*(?:,|to\b|each\b)", text[right.start():]):
        return "right"  # A right to receive shares is not the underlying share.
    for pattern, form in (
        (r"\b(preferred|preference)\b", "preferred"),
        (r"\bwarrants?\b", "warrant"),
        (r"\b(american depositary|american depository|adrs?|adss?)\b", "adr"),
        (r"\bclosed[- ]end\b", "closed_end_fund"),
        (r"\b(common stock|common shares?|ordinary shares?)\b", "common_stock"),
        (r"\brights?\b", "right"),
    ):
        if re.search(pattern, text):
            return form
    return "unknown"


def _symbol(value):
    # CQS uses case-sensitive suffix markers (for example lower-case "p").
    # Uppercasing those strings can invent a different ordinary ticker. Keep
    # the exact source field in original_record, but do not make it a generic
    # routing alias; another explicit uppercase source symbol may be used.
    if not isinstance(value, str) or value != value.upper():
        return None
    try:
        return validate_ticker(value)
    except ProviderError:
        return None


def parse_nasdaq_directory(content, directory, *, retrieved_at):
    """Return validated records/provenance from one already-authorized file.

    The footer timezone is undocumented. Its calendar date and original local
    creation string are retained; no UTC publication instant is manufactured.
    """
    if directory not in SOURCES:
        raise ValueError("Unknown Nasdaq directory kind.")
    if not isinstance(content, bytes) or not 0 < len(content) <= 5_000_000:
        raise ValueError("The directory must contain at most five megabytes of bytes.")
    if not retrieved_at or datetime.fromisoformat(str(retrieved_at).replace("Z", "+00:00")).tzinfo is None:
        raise ValueError("An explicit timezone-aware retrieval timestamp is required.")
    text = content.decode("utf-8-sig", errors="strict")
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 3 or len(lines) > 100_002:
        raise ValueError("The directory has an invalid bounded row count.")
    footer = lines[-1].split("|")[0]
    match = re.fullmatch(r"File Creation Time:\s*(\d{8}\d{2}:?\d{2})", footer)
    if not match:
        raise ValueError("A complete directory creation footer is required.")
    raw_clock = match.group(1)
    try:
        published = datetime.strptime(raw_clock, "%m%d%Y%H:%M" if ":" in raw_clock else "%m%d%Y%H%M")
    except ValueError:
        raise ValueError("The directory creation footer has an invalid date.") from None
    reader = csv.DictReader(io.StringIO("\n".join(lines[:-1])), delimiter="|")
    required = ({"Symbol", "Security Name", "Market Category", "Test Issue", "Financial Status", "Round Lot Size"}
                if directory == "nasdaqlisted" else
                {"ACT Symbol", "Security Name", "Exchange", "CQS Symbol", "ETF", "Round Lot Size", "Test Issue", "NASDAQ Symbol"})
    headers = reader.fieldnames or []
    allowed = required | ({"ETF", "NextShares"} if directory == "nasdaqlisted" else set())
    if not required <= set(headers) or set(headers) - allowed or len(set(headers)) != len(headers):
        raise ValueError("Unexpected directory schema; quarantine the source before import.")
    source_url = SOURCES[directory]
    records, seen, skipped_test, unsupported = [], set(), 0, []
    input_rows = 0
    for raw in reader:
        input_rows += 1
        if None in raw or any(value is None for value in raw.values()):
            raise ValueError("A directory row does not match its declared columns.")
        raw = {key: value.strip() for key, value in raw.items()}
        if raw["Test Issue"] not in {"Y", "N"} or raw.get("ETF", "N") not in {"Y", "N"}:
            raise ValueError("Unknown test-issue or ETF flag; quarantine the source.")
        if raw["Test Issue"] == "Y":
            skipped_test += 1
            continue
        source_symbol = raw["Symbol" if directory == "nasdaqlisted" else "ACT Symbol"]
        # Some ACT preferred/warrant conventions contain characters disallowed
        # by API routes. An explicitly supplied alternative is evidence; a
        # mechanical punctuation rewrite would not be.
        ticker = _symbol(source_symbol) or (_symbol(raw.get("NASDAQ Symbol", "")) if directory == "otherlisted" else None) or (
            _symbol(raw.get("CQS Symbol", "")) if directory == "otherlisted" else None)
        if not ticker:
            unsupported.append(source_symbol)
            continue
        if not raw["Security Name"] or len(raw["Security Name"]) > 500:
            raise ValueError("A directory security description is missing or too long.")
        venue, mic = (("NASDAQ", "XNAS") if directory == "nasdaqlisted" else EXCHANGES.get(raw["Exchange"], (raw["Exchange"], None)))
        key = source_symbol + "|" + (raw.get("Exchange") or "NASDAQ")
        if key in seen:
            raise ValueError("A directory contains duplicate source security rows.")
        seen.add(key)
        aliases = sorted({alias for name in ("CQS Symbol", "NASDAQ Symbol")
                          if (alias := _symbol(raw.get(name, ""))) and alias != ticker})
        description = raw["Security Name"]
        form = security_form(description, raw.get("ETF", "N"))
        share = re.search(r"\bClass\s+([A-Za-z0-9-]+)\b", description, flags=re.I)
        warnings = ["Directory membership does not prove uninterrupted trading or a listing commencement date."]
        if directory == "nasdaqlisted" and raw.get("Financial Status") not in {"", "N"}:
            warnings.append("Nasdaq financial-status flag " + raw["Financial Status"] + " is a deficiency/bankruptcy notice, not a trading suspension.")
        if mic is None:
            warnings.append("The source exchange code is not mapped to a supported US listing venue.")
        if form == "unknown":
            warnings.append("Security description and ETF flag do not establish an instrument classification.")
        row_hash = hashlib.sha256(json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        records.append({"ticker": ticker, "display_symbol": source_symbol, "name": description[:300],
                        "security_description": description, "exchange": venue, "exchange_mic": mic,
                        "source_record_key": key, "source_security_identifier": None,
                        "source_record_hash": row_hash, "original_record": raw,
                        "instrument_type": form, "security_form": form, "share_class": share.group(1) if share else None,
                        "listing_status": "active" if mic else "unknown", "identity_status": "reference_only",
                        "symbol_aliases": aliases, "classification_evidence": ({"provider": "nasdaq-trader",
                         "url": source_url, "description": description, "ETF": raw.get("ETF"),
                         "parser_version": PARSER_VERSION, "type_verified": True} if form != "unknown" else {}),
                        "warnings": warnings, "source_refs": [{"provider": "nasdaq-trader", "url": source_url,
                         "observed_on": published.date().isoformat(), "record_hash": row_hash,
                         "scope": "Dated directory membership and explicit security description; issuer CIK not provided."}]})
    if not records:
        raise ValueError("The directory contains no supported non-test security records.")
    if unsupported and len(unsupported) / max(1, input_rows - skipped_test) > .1:
        raise ValueError("Too many unsupported security symbols; quarantine the source.")
    return {"records": records, "provenance": {
        "source": "nasdaq-trader-" + directory, "source_kind": "listing_authority",
        "as_of": published.date().isoformat(), "published_at": raw_clock, "source_timezone": None,
        "retrieved_at": str(retrieved_at), "source_url": source_url,
        "content_hash": hashlib.sha256(content).hexdigest(), "complete_scope": True,
        "scope": "Dated non-test directory membership; omitted securities are not inferred delisted.",
        "rights": "Local audited use; public display and redistribution rights require operator confirmation.",
        "version": PARSER_VERSION, "quality": {"input_rows": input_rows, "accepted_rows": len(records),
        "excluded_test_issues": skipped_test, "unsupported_symbol_count": len(unsupported),
        "unsupported_symbols": unsupported[:100]},
        "notes": ["Source footer timezone is undocumented; publication is preserved without an invented UTC offset.",
                  "Directory symbols are source identifiers, not permanent security identifiers."]}}
