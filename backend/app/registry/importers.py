"""Offline parsers only. Download/rights approval belongs to the operator."""
import argparse
import hashlib
import json
from pathlib import Path

from app.providers.base import normalize_cik, ProviderError, validate_ticker
from app.registry.repository import SecurityRegistryRepository


def sec_reference_records(payload, *, source_url="https://www.sec.gov/files/company_tickers_exchange.json"):
    """Read SEC reference columns without claiming listing/security completeness.

    SEC CIK/title/ticker/exchange references do not establish common-stock type,
    active status, an ADR ratio, or entitlement to market-data endpoints.
    """
    if isinstance(payload, dict) and isinstance(payload.get("fields"), list) and isinstance(payload.get("data"), list):
        rows = [dict(zip(payload["fields"], values)) for values in payload["data"] if isinstance(values, list)]
    elif isinstance(payload, dict):
        rows = [row for row in payload.values() if isinstance(row, dict)]
    else:
        raise ValueError("Unsupported SEC reference format.")
    records = []
    for row in rows:
        cik, ticker, name = row.get("cik", row.get("cik_str")), row.get("ticker"), row.get("name", row.get("title"))
        if not (cik and ticker and name):
            continue
        try:
            cik, ticker = normalize_cik(cik), validate_ticker(ticker)
        except ProviderError:
            continue  # Unsupported symbol syntax cannot enter provider routes.
        records.append({"ticker": ticker, "name": name, "cik": cik, "exchange": row.get("exchange"),
                        "instrument_type": "unknown", "listing_status": "unknown", "identity_status": "reference_only",
                        "source_refs": [{"provider": "sec-edgar", "url": source_url,
                                         "scope": "SEC registrant/ticker reference; security type and active listing unverified."}]})
    return records


def import_file(repository, path):
    """Import an audited {records, provenance} JSON file without network access."""
    bundle = json.loads(Path(path).read_text(encoding="utf-8"))
    return repository.import_snapshot(bundle["records"], bundle["provenance"])


def import_sec_file(repository, path, as_of):
    """Import an operator-acquired SEC file, preserving its exact source hash."""
    content = Path(path).read_bytes()
    if len(content) > 5_000_000:
        raise ValueError("The SEC reference snapshot exceeds the supported size.")
    records = sec_reference_records(json.loads(content.decode("utf-8")))
    return repository.import_snapshot(records, {"source": "sec-edgar-reference", "as_of": as_of,
        "source_url": "https://www.sec.gov/files/company_tickers_exchange.json", "complete_scope": False,
        "scope": "SEC registrant/ticker references; active listing and security type unverified.",
        "rights": "Official public SEC reference; observe SEC fair-access policy.", "version": "sec-exchange-reference-1",
        "notes": ["Source SHA256 " + hashlib.sha256(content).hexdigest()]})


def main():
    parser = argparse.ArgumentParser(description="Import an authorized local security reference snapshot.")
    parser.add_argument("path")
    parser.add_argument("--sec-reference", action="store_true", help="Parse an already acquired SEC ticker/exchange file.")
    parser.add_argument("--as-of", help="Required ISO source snapshot date with --sec-reference.")
    args = parser.parse_args()
    if args.sec_reference and not args.as_of:
        parser.error("--sec-reference requires an explicit --as-of date")
    from app.core.config import get_settings
    from app.core.database import build_engine, build_session_factory
    engine = build_engine(get_settings().database_url)
    try:
        repository = SecurityRegistryRepository(build_session_factory(engine))
        result = import_sec_file(repository, args.path, args.as_of) if args.sec_reference else import_file(repository, args.path)
        print(json.dumps(result))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
