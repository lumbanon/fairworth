"""Offline eleven-model audit from dated, maintained public excerpts.

Requires development/test dependencies. No application settings, database or HTTP
providers are accessed. The SQLite registry exists only for this bounded replay.
"""
import argparse
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BACKEND), str(BACKEND / "tests")]
import httpx
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from app.core.database import Base, build_session_factory
import app.models
from app.valuation.coverage import enrich_valuation_coverage, summarize_coverage
from app.valuation.engine import calculate_valuation
from phase66_coverage_helpers import captured_listings, import_captured_listings, replay_verified_sample
from app.registry.service import SecurityRegistryService
from app.services.automatic_inputs_service import original_annual_periods
from app.services.normalization import normalize_company_facts
from app.valuation.automatic import prepare_automatic_inputs
from app.valuation.inputs import build_valuation_inputs
from test_ai_evidence_context import retained_inputs


def replay_approved_excerpts():
    """New financial evidence keeps the real, older listing-proof clocks."""
    fixture = json.loads((BACKEND / "tests/fixtures/valuation/phase67_sec_financial_excerpts_2026_10_20.json").read_text(encoding="utf-8"))
    clock = datetime.fromisoformat(fixture["as_of"])
    assert fixture["data_mode"] == "newly_approved_live" and clock.tzinfo is not None
    metadata = json.loads((BACKEND / "tests/fixtures/registry/sec_reference_sample_2026_10_18.json").read_text(encoding="utf-8"))
    companies = retained_inputs()
    sectors = {row["requested_symbol"]: row.get("submissions") or {} for row in metadata["samples"]}
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    def blocked(*_args, **_kwargs):
        raise RuntimeError("HTTP is forbidden during approved-evidence replay.")
    async def async_blocked(*_args, **_kwargs):
        blocked()
    rows = []
    async def assemble(factory):
        listings, repository, _ = import_captured_listings(factory)
        registry = SecurityRegistryService(factory, SimpleNamespace(registry_bootstrap_enabled=False, registry_cache_ttl_seconds=86400))
        for entry in fixture["issuers"]:
            symbols = [entry["symbol"]] + (["GOOG"] if entry["symbol"] == "GOOGL" else [])
            source = entry["source"]
            if source["url"] != f"https://data.sec.gov/api/xbrl/companyfacts/CIK{entry['cik']}.json" or datetime.fromisoformat(source["retrieved_at"]) > clock:
                raise ValueError("Approved fixture source scope or audit clock is invalid.")
            for symbol in symbols:
                captured = next(sample for sample in listings["samples"] if sample["requested_symbol"] == symbol)
                candidates = [row for row in repository.search(symbol, 50)["results"] if row["listing_verification"].get("record_hash") == captured["listing_record"]["source_record_hash"]]
                if len(candidates) != 1:
                    raise ValueError("Exact dated listing proof no longer resolves uniquely.")
                selected = candidates[0]
                company = await registry.resolve(selected["ticker"], selected["instrument_id"], selected["listing_id"])
                if str(entry["raw"]["cik"]).zfill(10) != entry["cik"] or company.get("cik") != entry["cik"]:
                    raise ValueError("Approved financial evidence does not match the selected reporting issuer.")
                # Original profile/class metadata remains dated; current listing
                # resolution takes precedence. No fresh profile is fabricated.
                company = {**companies.get(symbol, {}).get("company", {}), **company}
                details = sectors.get(symbol, {})
                sic = str(details.get("sic") or "")
                if sic.isdigit():
                    bank = sic in {"6021", "6022", "6029", "6035", "6036", "6061", "6062", "6081", "6082", "6099"}
                    reit = sic == "6798"
                    company.update(sic=sic, industry=details.get("sicDescription"), is_bank=bank, is_reit=reit,
                        issuer_business_category="bank" if bank else "reit" if reit else "insurance" if 6300 <= int(sic) <= 6399 else "other" if 6000 <= int(sic) <= 6999 else "operating_company")
                    company["issuer_classification_evidence"] = {"provider": "sec-edgar", "concept": "sic", "value": sic, "as_of": "2026-10-18"}
                normalized = normalize_company_facts(entry["raw"], cik=entry["cik"])
                inputs = build_valuation_inputs({"company": company, "warnings": company.get("registry_warnings", [])}, normalized, source["retrieved_at"])
                native = original_annual_periods(entry["raw"], normalized, company, source["retrieved_at"])
                evidence = {"historical_annual_periods": native, "as_of_date": source["retrieved_at"][:10],
                    "observations": {}, "splits": {"complete": False, "status": "not_acquired", "splits": []},
                    "historical_prices": {"status": "not_acquired", "prices": []},
                    "financial_snapshot_date": source["retrieved_at"],
                    "provider_status": {"market": "not_acquired", "treasury": "not_acquired"}}
                inputs = prepare_automatic_inputs(inputs, evidence)
                inputs["financial_source_status"] = {"status": "fresh", "provider": "sec-edgar"}
                inputs["data_status"] = "partial"
                result = enrich_valuation_coverage(inputs, calculate_valuation(inputs), as_of=fixture["as_of"])
                row = result["financial_coverage"]
                row.update(symbol=symbol, data_mode="newly_approved_live", financial_source=deepcopy(source),
                    fair_value=result["scenarios"]["base"]["summary"]["fair_value"],
                    classification=result["scenarios"]["base"]["summary"].get("classification"),
                    native_common_eps_verified_periods=sum(period.get("reported_common_eps_basis_verified") is True for period in native),
                    source_scope="Curated original annual fields; full downloaded source counts are reported separately.")
                rows.append(deepcopy(row))
    try:
        Base.metadata.create_all(engine)
        with patch.object(httpx.HTTPTransport, "handle_request", blocked), patch.object(httpx.AsyncHTTPTransport, "handle_async_request", async_blocked), patch("app.registry.service.utcnow", return_value=clock):
            asyncio.run(assemble(build_session_factory(engine)))
        report = summarize_coverage(sorted(rows, key=lambda row: row["symbol"]), as_of=fixture["as_of"], data_mode="newly_approved_live")
        report.update(source_issuer_denominator=len(fixture["issuers"]), acquisition=fixture["acquisition"],
            limitations=report["limitations"] + fixture["limitations"] + ["Eight approved issuer documents cover nine separately gated securities because GOOG and GOOGL share one issuer. No per-class values are transferred."])
        return report
    finally:
        engine.dispose()


def replay():
    clock = captured_listings()["audit_as_of"]
    records = {}
    def capture(inputs, *args, **kwargs):
        result = calculate_valuation(inputs, *args, **kwargs)
        enriched = enrich_valuation_coverage(inputs, result, as_of=clock)
        row = enriched["financial_coverage"]
        row.update(symbol=inputs["company"]["ticker"], data_mode="retained_public",
                   fair_value=result["scenarios"]["base"]["summary"]["fair_value"],
                   classification=result["scenarios"]["base"]["summary"].get("classification"))
        records[row["identity"]["listing_id"]] = deepcopy(row)
        return result
    def blocked(*_args, **_kwargs):
        raise RuntimeError("HTTP is forbidden during the dated financial replay.")
    async def async_blocked(*_args, **_kwargs):
        blocked()
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    try:
        Base.metadata.create_all(engine)
        with patch.object(httpx.HTTPTransport, "handle_request", blocked), patch.object(httpx.AsyncHTTPTransport, "handle_async_request", async_blocked), patch("phase66_coverage_helpers.calculate_valuation", side_effect=capture):
            asyncio.run(replay_verified_sample(build_session_factory(engine)))
        return summarize_coverage(sorted(records.values(), key=lambda item: item["symbol"]), as_of=clock, data_mode="retained_public")
    finally:
        engine.dispose()


def markdown(report):
    lines = [f"Financial model audit: {report['data_mode']}; offline replay makes no provider requests.",
             f"As of {report['as_of']}; denominator {report['sample_denominator']} securities.", "",
             "| Stage | Available / sampled |", "| --- | --- |"]
    lines += [f"| {key} | {part['numerator']} / {part['denominator']} |" for key, part in report["stages"].items()]
    lines += ["", "| Security | Eligible / 11 | Contributing | Families | Published estimate classification |", "| --- | --- | --- | --- | --- |"]
    lines += [f"| {row['symbol']} | {row['eligible_model_count']} | {row['contributing_model_count']} | {len(row['contributing_model_families'])} | {row['classification']} |" for row in report["samples"]]
    lines += ["", "| Security | Model | Engine status | Blocker categories |", "| --- | --- | --- | --- |"]
    lines += [f"| {row['symbol']} | {model['id']} | {model['eligibility_status']} | {', '.join(part['code'] for part in model['blockers']) or 'None'} |" for row in report["samples"] for model in row["models"]]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output")
    parser.add_argument("--matrix-output")
    parser.add_argument("--approved-excerpts", action="store_true", help="Replay only the already approved dated financial excerpts, preserving expired listing proofs.")
    args = parser.parse_args()
    result = replay_approved_excerpts() if args.approved_excerpts else replay()
    if args.matrix_output:
        Path(args.matrix_output).write_text(markdown(result), encoding="utf-8")
    raw = json.dumps(result, indent=2, default=str) + "\n"
    if args.output:
        Path(args.output).write_text(raw, encoding="utf-8")
    else:
        print(raw, end="")


if __name__ == "__main__":
    main()
