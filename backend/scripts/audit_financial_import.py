"""Inspect a retained approved SEC document against the existing DB; never import."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.services.financial_import_audit import audit_financial_import, load_approved_sec_source, read_only_connection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--instrument-id")
    parser.add_argument("--listing-id")
    parser.add_argument("--as-of", required=True, help="Explicit zoned audit clock; never substitutes for source retrieval.")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.resolve() in {args.source.resolve(), args.manifest.resolve()}:
        parser.error("The report destination must not overwrite the original source or acquisition manifest.")
    raw, source = load_approved_sec_source(args.source, args.manifest)
    settings = Settings()
    url = make_url(settings.database_url)
    if url.get_backend_name() != "postgresql" or url.host not in {"127.0.0.1", "localhost"}:
        parser.error("Only the existing configured local PostgreSQL database is supported; no database is created.")
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    try:
        with read_only_connection(engine) as connection:
            result = audit_financial_import(connection, raw, source, ticker=args.ticker, as_of=args.as_of,
                sec_cache_ttl_seconds=settings.sec_cache_ttl_seconds, instrument_id=args.instrument_id, listing_id=args.listing_id)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, default=str, allow_nan=False), encoding="utf-8")
        print(json.dumps({"mode": result["mode"], "ticker": args.ticker, "executed_writes": 0,
                          "facts": {key: result["facts"][key] for key in ("already_persisted", "new_observations", "same_filing_conflicts")}}))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
