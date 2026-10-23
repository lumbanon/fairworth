"""Explicit, bounded local IBKR research session; never used by FastAPI.

Without --connect this prints a plan and performs no SDK import or connection.
Identity is read from the existing registry, never accepted from an arbitrary
provider ticker. Personal observations can only be retained under .phase68.local.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
import hashlib
import json
import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings
from app.core.database import build_engine, build_session_factory
from app.providers.base import ProviderError, validate_ticker
from app.providers.ibkr import IbkrAuthorization, IbkrConnection, IbkrMarketDataProvider, PRIVATE
from app.registry.repository import SecurityRegistryRepository

ROOT = Path(__file__).resolve().parents[2]


def private_output(path):
    destination = Path(path).resolve()
    directory = (ROOT / ".phase68.local").resolve()
    if not directory.is_relative_to(ROOT) or not destination.is_relative_to(directory) or destination == directory or destination.suffix != ".json":
        raise ValueError("Personal broker observations may only be written as JSON under ignored .phase68.local/.")
    if destination.exists():
        raise ValueError("The output already exists; private original observations are never overwritten.")
    # Reject existing symlink/junction parents that resolve out of the directory.
    return destination


async def execute(args):
    settings = Settings()
    connection = IbkrConnection(host=settings.ibkr_host, port=settings.ibkr_port, client_id=settings.ibkr_client_id,
                                timeout_seconds=settings.ibkr_timeout_seconds)
    symbol = validate_ticker(args.symbol)
    plan = {"connection_method": "official_tws_api", "host": connection.host, "port": connection.port,
            "selected_identity": {"ticker": symbol, "instrument_id": args.instrument_id, "listing_id": args.listing_id},
            "client_id": connection.client_id, "symbols": [symbol], "contract_lookups": 1, "quote_requests": 1,
            "historical_requests": int(bool(args.history_days)), "history_days": args.history_days,
            "timeout_seconds_per_operation": connection.timeout_seconds, "minimum_start_interval_seconds": 1,
            "max_quote_subscription_seconds": min(12, connection.timeout_seconds), "automatic_retries": 0,
            "regulatory_snapshots": False, "market_data_type_requested": args.market_data_type,
            "account_requests": 0, "trading_requests": 0, "public_export": False,
            "retention": "none" if not args.output else "ignored_local_json_requires_explicit_retention_confirmation"}
    if not args.connect:
        print(json.dumps({"status": "not_connected", "plan": plan}, indent=2))
        return
    if not args.approval_reference or not args.confirm_personal_use or not args.confirm_api_non_display_use or not args.confirm_read_only:
        raise ValueError("Review this exact plan and obtain explicit user approval before using --connect; personal-use and read-only confirmations are mandatory.")
    if connection.port is None:
        raise ValueError("IBKR_PORT is unset. Confirm TWS versus IB Gateway and its actual configured port before approval/connection.")
    if args.output and not args.confirm_local_retention:
        raise ValueError("Local retention must be explicitly permitted by the applicable data agreement and approved before export.")
    destination = private_output(args.output) if args.output else None
    engine = build_engine(settings.database_url)
    try:
        # Registry repository resolution only: no provider, bootstrap, cache load,
        # company enrichment or application-level write is called by this CLI.
        identity = SecurityRegistryRepository(build_session_factory(engine)).resolve(symbol, instrument_id=args.instrument_id, listing_id=args.listing_id)
    finally:
        engine.dispose()
    if not identity:
        raise ValueError("The selected security is not present in the local registry.")
    authorization = IbkrAuthorization(approval_reference=args.approval_reference, symbols=(symbol,), max_contract_lookups=1,
            max_quotes=1, max_history_requests=int(bool(args.history_days)), market_data_type=args.market_data_type,
            personal_use_confirmed=True, api_non_display_use_confirmed=True, read_only_session_confirmed=True, local_retention_confirmed=args.confirm_local_retention)
    provider = IbkrMarketDataProvider(connection)
    # Official SDK debug logging may include unsolicited protocol frames. The
    # standalone local process suppresses all logging before importing that SDK.
    previous_logging = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        await provider.open(authorization)
        quote = await provider.quote(symbol, identity)
        history = await provider.historical_prices(symbol, args.history_days, identity) if args.history_days else []
        result = {"schema_version": "fairworth-private-ibkr-1", **PRIVATE, "plan": plan, "quote": quote, "history": history,
                  "scope": quote["identity"], "data_origin": "actual_ibkr", "source_retention": bool(destination),
                  "limitations": ["No independent listing status, financial-currentness, share-denominator or complete split-history proof is supplied by this session."]}
        if destination:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("x", encoding="utf-8") as stream:
                json.dump(result, stream, indent=2)
            print(json.dumps({"status": "private_observation_retained", "output": str(destination.relative_to(ROOT)),
                              "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(), "public_export": False}))
        else:
            # No financial values or contract/session details go into shared logs.
            print(json.dumps({"status": "private_session_completed", "market_data_type": quote["market_data_type"],
                              "has_source_timestamp": quote["price_timestamp"] is not None, "historical_bars": len(history), "retained": False}))
    finally:
        await provider.close()
        logging.disable(previous_logging)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", choices=("AAPL", "MSFT"), default="AAPL")
    parser.add_argument("--instrument-id", required=True)
    parser.add_argument("--listing-id", required=True)
    parser.add_argument("--history-days", type=int, choices=range(1, 32), default=None)
    parser.add_argument("--market-data-type", type=int, choices=(1, 2, 3, 4), default=1)
    parser.add_argument("--connect", action="store_true")
    parser.add_argument("--approval-reference")
    parser.add_argument("--confirm-personal-use", action="store_true")
    parser.add_argument("--confirm-api-non-display-use", action="store_true")
    parser.add_argument("--confirm-read-only", action="store_true")
    parser.add_argument("--confirm-local-retention", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()
    try:
        asyncio.run(execute(args))
    except ProviderError as error:
        print(json.dumps({"status": "unavailable", "code": error.code, "message": error.message}), file=sys.stderr)
        raise SystemExit(2) from None
    except (ValueError, OSError):
        # Do not print settings validation/source errors that may embed private
        # input values, paths or SQL connection details.
        print("The local plan, identity, evidence, output or configuration is invalid; no public data was published.", file=sys.stderr)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
