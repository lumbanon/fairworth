"""Offline Phase 6.7.2 audit with explicit separation of retained acquisitions."""
import argparse
import asyncio
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
from unittest.mock import patch

import httpx
import replay_phase671_valuation_coverage as previous
from phase671_evidence import load_local_evidence_manifest
from phase672_evidence import load_aapl_manifest


def apply_aapl_evidence(captured, inventory, clock):
    """Normalize one authorized bundle locally; never install it in the app DB."""
    from app.providers.market_data import FmpMarketDataProvider
    from app.providers.base import ProviderError
    from app.providers.capabilities import capability_record
    from app.services.security_identity import check_provider_identity
    from app.services.normalization import normalize_company_facts
    from app.services.automatic_inputs_service import original_annual_periods
    from app.valuation.inputs import build_valuation_inputs
    from app.valuation.automatic import prepare_automatic_inputs
    from app.valuation.financial_currentness import unverified_currentness

    source, records = deepcopy(captured)
    if "AAPL" not in records:
        return (source, records), {"applied": False, "reason": "AAPL is outside this population; denominators are preserved."}
    entries = {(row["provider"], row["endpoint"]): row for row in inventory["inventory"]}
    original, historical = records["AAPL"]
    company = original["company"]
    if company.get("cik") != "0000320193":
        raise ValueError("AAPL evidence cannot be transferred to a different selected issuer.")
    class LocalProvider(FmpMarketDataProvider):
        async def _records(self, endpoint, ticker, parameters=None, identity=None):
            record = entries.get(("fmp", endpoint))
            if not record or record["status"] != "received":
                raise ProviderError("provider_subscription_required", "The bounded audit did not establish access to this endpoint.", 503)
            for row in record["payload"]:
                check_provider_identity(identity, row)
            return deepcopy(record["payload"])
    adapter = LocalProvider(None, api_key="")
    async def normalize_market():
        for endpoint in ("profile", "quote"):
            entry = entries.get(("fmp", endpoint))
            if not entry or entry["status"] != "received":
                if endpoint == "quote": return None
                continue
            acquired = previous.instant(entry["retrieved_at"])
            class SourceClock(datetime):
                @classmethod
                def now(cls, tz=None):
                    return acquired.astimezone(tz) if tz else acquired.replace(tzinfo=None)
            class AuditClock(datetime):
                @classmethod
                def now(cls, tz=None):
                    return clock.astimezone(tz) if tz else clock.replace(tzinfo=None)
            with patch("app.providers.market_data.datetime", SourceClock), patch("app.providers.currency.datetime", AuditClock):
                response = await getattr(adapter, endpoint)("AAPL", identity=company)
            if endpoint == "quote": return response
    market = asyncio.run(normalize_market())
    if market:
        market.update(source_type="api", status="fresh", provider_currency=market.get("currency"))
        for (provider, endpoint), entry in entries.items():
            if provider != "fmp": continue
            error = "provider_subscription_required" if entry.get("http_status") == 402 else None if entry["status"] == "received" else "provider_access_denied"
            market["provider_capabilities"]["endpoints"][endpoint] = capability_record(endpoint,
                observed_at=entry["retrieved_at"], error_code=error, success=entry["status"] == "received")
    facts = entries.get(("sec", "companyfacts"))
    if facts and facts["status"] == "received":
        normalized = normalize_company_facts(facts["payload"], cik=company["cik"])
        inputs = build_valuation_inputs({"company": company, "market": market}, normalized, facts["retrieved_at"])
        evidence = deepcopy(original.get("automatic_evidence", {}))
        evidence["historical_annual_periods"] = original_annual_periods(facts["payload"], normalized, company, facts["retrieved_at"])
        evidence["financial_snapshot_date"] = facts["retrieved_at"]
        evidence["as_of_date"] = clock.date().isoformat()
        split = entries.get(("fmp", "splits"))
        evidence["retained_historical_splits"] = evidence.get("splits")
        evidence["splits"] = {"complete": False, "status": "provider_subscription_required" if split and split.get("http_status") == 402 else "not_verified",
            "splits": [], "reason": "Current split completeness was not established; dated historical split evidence is not renewed by a quote."}
        evidence.setdefault("provider_status", {})["splits"] = evidence["splits"]["status"]
        inputs = prepare_automatic_inputs(inputs, evidence)
        inputs["financial_source_status"] = {"status": "audit_only", "currentness": unverified_currentness(),
            "reason": "New source is normalized only in isolated replay; no application cache import or reviewed currentness assessment is implied."}
        inputs["data_status"] = "partial"
    else:
        inputs = deepcopy(original)
        inputs["market"] = market
    records["AAPL"] = inputs, historical
    return (source, records), {"applied": True, "scope": "AAPL only, isolated normalization and calculation", "production_writes": 0,
        "quote_currency_status": (market or {}).get("currency_resolution", {}).get("status"),
        "quote_observed_at": (market or {}).get("price_timestamp"), "quote_retrieved_at": (market or {}).get("retrieved_at"),
        "current_split_scope": "unverified", "financial_currentness_policy": "unverified"}


def replay(population, as_of, *, prior_manifest=None, authorization_receipt=None, new_manifest=None, new_receipt=None):
    def blocked(*_args, **_kwargs):
        raise RuntimeError("This replay never makes provider requests.")
    async def async_blocked(*_args, **_kwargs):
        blocked()
    with patch.object(httpx.HTTPTransport, "handle_request", blocked), patch.object(httpx.AsyncHTTPTransport, "handle_async_request", async_blocked):
        captured = previous.capture(population)
        inventory = None
        if prior_manifest:
            if not authorization_receipt:
                raise ValueError("An exact prior acquisition receipt is required; this does not authorize new acquisition.")
            inventory = load_local_evidence_manifest(prior_manifest, audit_clock=as_of, expected_authorization_question_id=authorization_receipt)
            captured = previous.apply_local_updates(population, captured, inventory, previous.instant(as_of))
        new_inventory, application = None, None
        if new_manifest:
            if not new_receipt: raise ValueError("New acquisition receipt is required independently of old evidence.")
            new_inventory = load_aapl_manifest(new_manifest, audit_clock=as_of, authorization_receipt=new_receipt)
            captured, application = apply_aapl_evidence(captured, new_inventory, previous.instant(as_of))
        report = previous.build_matrix(population, as_of, captured=captured)
    report["phase"] = "6.7.2"
    report["evidence_collections"] = {
        "base_financial_evidence": "retained_phase67_fixtures" if population == "retained" else "previously_approved_phase67_sec_excerpt",
        "previous_phase671_acquisition": ({"request_count": inventory["actual_requests"], "bytes": inventory["actual_bytes"],
            "sources": [{key: row[key] for key in ("provider", "endpoint", "symbol", "status", "http_status", "retrieved_at", "sha256", "bytes") if key in row} for row in inventory["inventory"]]} if inventory else None),
        "new_phase672_acquisitions": new_inventory["safe_metadata"] if new_inventory else [],
        "new_evidence_application": application, "mocked_or_synthetic_evidence_in_coverage": False}
    report["limitations"] += ["Prior acquisition receipts authorize no new requests or database imports.",
        "Observed access is dated evidence, not current endpoint entitlement or display rights.",
        "No reviewed source-backed financial currentness policy or new financial input is inferred from metadata."]
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--population", choices=("retained", "approved"), required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--prior-manifest", type=Path)
    parser.add_argument("--authorization-receipt")
    parser.add_argument("--new-aapl-manifest", type=Path)
    parser.add_argument("--new-authorization-receipt")
    parser.add_argument("--compare", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args()
    report = replay(args.population, args.as_of, prior_manifest=args.prior_manifest, authorization_receipt=args.authorization_receipt,
        new_manifest=args.new_aapl_manifest, new_receipt=args.new_authorization_receipt)
    if args.compare:
        report["comparison"] = previous.compare_reports(json.loads(args.compare.read_text(encoding="utf-8")), report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, default=str, allow_nan=False) + "\n", encoding="utf-8")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(previous.markdown(report).replace("Phase 6.7.1", "Phase 6.7.2"), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("population", "security_denominator", "model_pair_denominator", "historical_model_securities", "current_eligible_securities", "current_published_securities")}))


if __name__ == "__main__":
    main()
