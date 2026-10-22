"""Explicit-clock, HTTP-blocked model blocker audit of maintained evidence.

The two populations retain separate denominators. Registry UUIDs are deterministic
fixture identities, never represented as IDs from a user's production database.
"""
import argparse
import asyncio
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import UTC, datetime
import itertools
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5

BACKEND = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BACKEND), str(BACKEND / "tests")]
import httpx
import replay_financial_model_coverage as legacy
from app.registry.service import SecurityRegistryService
from app.valuation.coverage import MODEL_ASSUMPTIONS, enrich_valuation_coverage
from app.valuation.engine import calculate_valuation, calculation_values
from app.valuation.models import required_inputs
from app.valuation.weighting import GROUPS
from phase671_evidence import load_local_evidence_manifest

CONTRACTS = {
    "fcff": ("Operating-company enterprise cash flows; complete non-overlapping EV bridge", "Explicit projection path or complete reviewed operating components; source-backed growth windows for automatic forecasts", "WACC, terminal growth and reinvestment; never replace missing facts with policy"),
    "fcfe": ("Common-equity cash flows; complete financing scope", "Explicit equity projection or complete reviewed operating/financing components", "Cost of equity and terminal growth; no second debt deduction"),
    "pe": ("Positive selected-security common EPS; suitable earnings-based business", "Explicit supported forward EPS or trailing EPS plus permitted growth; automatic own-history multiple requires three qualifying distinct fiscal years", "Target P/E, forward-earnings basis; own history is not a peer multiple"),
    "evEbitda": ("Industrial enterprise methods; complete company-wide EBITDA and EV bridge", "Supported EBITDA forecast or complete revenue/margin path; automatic multiple requires three qualifying years", "Sourced target EV/EBITDA and supported forecast; narrow PP&E D&A is insufficient"),
    "evRevenue": ("Suitable industrial revenue method with complete EV bridge", "Supported forecast or revenue/growth; automatic multiple requires three qualifying years", "Sourced target EV/revenue and revenue forecast"),
    "peg": ("Positive common EPS and economically valid positive growth", "Supported forward EPS or trailing EPS; automatic growth needs four consecutive compatible annual endpoints", "Supported target PEG and growth; shares EPS/growth dependencies with P/E"),
    "graham": ("Positive applicable common EPS and meaningful verified common book equity", "One compatible earnings/book basis; no numerical forecast required", "No invented common-equity adjustments; existing applicability policy remains authoritative"),
    "dividend": ("Dividend-paying common security with sustainable per-share payout", "Supported per-share dividend/growth or explicit supported dividend projection", "Cost of equity above sustainable growth; total dividends are not dividends per share"),
    "residual": ("Common equity with clean-surplus-compatible projections", "Verified common book plus supported ROE/payout path", "Cost of equity and terminal growth; industrial EV bridge not substituted"),
    "pb": ("Meaningful common book equity; sector-appropriate book multiple", "Verified common book/share basis; automatic target requires three qualifying fiscal years", "Sourced or explicitly allowed target P/B; consolidated equity is not automatically common equity"),
    "affo": ("REIT with auditable issuer-specific complete AFFO definition", "Supported AFFO forecast and corresponding shares; generic OCF/EBITDA insufficient", "Supported target P/AFFO; no manufactured AFFO"),
}


def financial_compatibility(inputs, values, paths, model_id, incompatible, checks):
    """Separate reported-input scope/basis from numerical assumption completion."""
    basis = {key: deepcopy(checks[key]) for key in ("share_basis", "currency", "reporting_regime")}
    observed_paths = [sorted(set(path) - MODEL_ASSUMPTIONS[model_id]) for path in paths]
    supported = any(all(values.get(field) is not None and field not in incompatible for field in path)
                    for path in observed_paths)
    compatible = supported and all(check["status"] == "available" for check in basis.values())
    return {"compatible": compatible, "basis": basis, "reported_input_paths": observed_paths,
            "reported_path_available": supported,
            "scope_incompatible_fields": incompatible,
            "limitation": "This assessment excludes numerical assumptions and economic eligibility; the engine remains authoritative."}


def rank_blockers(rows):
    groups = defaultdict(lambda: {"models": set(), "symbols": set(), "fields": set()})
    for row in rows:
        if row["economic_appropriateness"] == "ineligible":
            continue  # Inappropriate frameworks are not potential coverage gains.
        for blocker in row["blockers"] + row.get("publication_blockers", []):
            group = groups[blocker["code"]]
            group["models"].add((row["symbol"], row["model_id"]))
            group["symbols"].add(row["symbol"])
            group["fields"].update(blocker.get("fields", []))
    ranking = []
    for code, group in groups.items():
        reference = any(word in code for word in ("verification", "identity", "active_security"))
        market = "quote" in code
        rate = "discount_rate" in code
        ranking.append({"code": code, "potentially_appropriate_security_model_pairs": len(group["models"]),
            "affected_securities": len(group["symbols"]), "fields": sorted(group["fields"]),
            "financial_materiality": "Publication safety" if reference or market else "Required model input; missing amounts are never zero",
            "retained_resolution": "No: current official evidence required" if reference or market else "Partial: exact original source scope must be reviewed; fixture absence is inconclusive",
            "provider_and_licensing": "Fresh acquisition approval and source rights required" if reference or market else "No acquisition implied; exact filing or entitled provider may be needed",
            "complexity_and_risk": "Bounded reference reconciliation; preserve independent clocks" if reference else "Quote identity, currency and observation causality" if market else "High economic-scope risk; no generic proxy" if rate else "Input-specific accounting and period review",
            "resolution": "Conditional affected pairs, not promised additional valid models; all other blockers remain."})
    return sorted(ranking, key=lambda row: (-row["potentially_appropriate_security_model_pairs"], -row["affected_securities"], row["code"]))


def instant(raw):
    value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("Audit clocks require an explicit timezone.")
    return value.astimezone(UTC)


def capture(population):
    records = {}
    sequence = itertools.count()
    def identifier():
        return uuid5(NAMESPACE_URL, f"fairworth-phase671-fixture:{population}:{next(sequence)}")
    def collect(inputs, *args, **kwargs):
        result = calculate_valuation(inputs, *args, **kwargs)
        records[inputs["company"]["ticker"]] = (deepcopy(inputs), deepcopy(result))
        return result
    replay = legacy.replay if population == "retained" else legacy.replay_approved_excerpts
    with patch("app.models.security_registry.uuid4", side_effect=identifier), patch.object(legacy, "calculate_valuation", side_effect=collect):
        source_report = replay()
    return source_report, records


def apply_local_updates(population, captured, inventory, clock):
    """Reconcile approved local source bytes in disposable SQLite, never app DB.

    Existing fixture identities must survive exactly. No financial fact, scope
    policy, split, currency or source-cache clock is manufactured by a refresh.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool
    from app.core.database import Base, build_session_factory
    from app.registry.importers import sec_reference_records
    from app.providers.base import ProviderError
    from app.providers.market_data import FmpMarketDataProvider
    from app.services.security_identity import check_provider_identity

    source, original_records = captured
    records = deepcopy(original_records)
    wanted = {item[0]["company"]["ticker"] for item in records.values()}
    wanted |= {item[0]["company"].get("display_symbol") for item in records.values()}
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sequence = itertools.count()
    def identifier():
        return uuid5(NAMESPACE_URL, f"fairworth-phase671-fixture:{population}:{next(sequence)}")
    async def update(factory):
        _, repository, _ = legacy.import_captured_listings(factory)
        for item in inventory["inventory"]:
            if item["status"] != "received":
                continue
            if item["provider"] == "sec":
                entries = [entry for entry in sec_reference_records(item["payload"]) if entry["ticker"] in wanted]
                provenance = {"source": "sec-edgar-reference", "as_of": item["retrieved_at"][:10],
                    "source_url": item["url"], "retrieved_at": item["retrieved_at"], "content_hash": item["sha256"],
                    "complete_scope": False, "scope": "Exact selected records from authorized directory; retrieval snapshot date is not a filing date."}
                repository.import_snapshot(entries, provenance)
            elif item["provider"] == "nasdaq":
                payload = item["payload"]
                entries = [entry for entry in payload["records"] if entry["ticker"] in wanted or wanted.intersection(entry.get("symbol_aliases", []))]
                repository.import_snapshot(entries, {**payload["provenance"], "complete_scope": False,
                    "scope": "Exact selected records from authorized full directory; original source clocks and hash retained."})
        registry = SecurityRegistryService(factory, SimpleNamespace(registry_bootstrap_enabled=False, registry_cache_ttl_seconds=86400))
        for symbol, (inputs, _historic) in records.items():
            previous = inputs["company"]
            company = await registry.resolve(previous["ticker"], previous["instrument_id"], previous["listing_id"])
            if any(company.get(key) != previous.get(key) for key in ("issuer_id", "instrument_id", "listing_id", "cik")):
                raise ValueError("Updated reference source changed the selected evidence identity; no financial transfer allowed.")
            inputs["company"] = {**previous, **company}
            for item in inventory["inventory"]:
                if item["provider"] != "fmp" or item["symbol"] != symbol or item["endpoint"] != "quote":
                    continue
                if item["status"] != "received":
                    inputs.setdefault("automatic_evidence", {}).setdefault("provider_status", {})["quote"] = "provider_subscription_required" if item.get("http_status") == 402 else item["status"]
                    continue
                class LocalQuote(FmpMarketDataProvider):
                    async def _records(self, *_args, **_kwargs):
                        for row in item["payload"]:
                            check_provider_identity(inputs["company"], row)
                        return deepcopy(item["payload"])
                    async def profile(self, *_args, **_kwargs):
                        raise ProviderError("provider_access_denied", "No profile was acquired in the bounded audit.", 503)
                adapter = LocalQuote(None, api_key="")  # Local raw-response adapter; _records never performs HTTP.
                adapter.stale_price_seconds = 172800
                acquired = instant(item["retrieved_at"])
                class SourceClock(datetime):
                    @classmethod
                    def now(cls, tz=None):
                        return acquired.astimezone(tz) if tz else acquired.replace(tzinfo=None)
                with patch("app.providers.market_data.datetime", SourceClock):
                    quote = await adapter.quote(symbol, identity=inputs["company"])
                quote.update(source_type="api", status="fresh", provider_currency=quote.get("currency"),
                    source_record={key: item[key] for key in ("url", "sha256", "retrieved_at", "bytes")})
                inputs["market"] = quote
    try:
        with patch("app.models.security_registry.uuid4", side_effect=identifier), patch("app.registry.service.utcnow", return_value=clock):
            asyncio.run(update(build_session_factory(engine)))
    finally:
        engine.dispose()
    return source, records


def build_matrix(population, as_of, *, captured=None):
    clock = instant(as_of)
    source, records = captured if captured is not None else capture(population)
    if instant(source["as_of"]) > clock:
        raise ValueError("Source evidence cannot follow the audit clock.")
    registry = object.__new__(SecurityRegistryService)
    registry.settings = SimpleNamespace(registry_cache_ttl_seconds=86400)
    rows = []
    securities = []
    for symbol, (original_inputs, historic) in sorted(records.items()):
        inputs = deepcopy(original_inputs)
        with patch("app.registry.service.utcnow", return_value=clock):
            inputs["company"] = registry._with_freshness(inputs["company"])
        current = enrich_valuation_coverage(inputs, calculate_valuation(inputs), as_of=clock.isoformat())
        company = inputs["company"]
        base = current["scenarios"]["base"]
        assumptions = base["assumptions"]
        values = calculation_values(inputs, assumptions)
        details = {item["id"]: item for item in current["financial_coverage"]["models"]}
        old_models = {item["id"]: item for item in historic["scenarios"]["base"]["models"]}
        completeness = base["data_completeness"]
        proof = company.get("listing_verification") or {}
        stale = [{"kind": "listing", **deepcopy(proof)}] if proof.get("freshness") != "fresh" else []
        linkage = company.get("issuer_linkage") or proof.get("issuer_linkage") or {}
        if linkage.get("freshness") != "fresh":
            stale.append({"kind": "issuer_linkage", **deepcopy(linkage)})
        if current["financial_coverage"]["stages"]["fresh_quote"]["status"] != "available":
            stale.append({"kind": "market_price", **deepcopy(current["market"])})
        restrictions = deepcopy(inputs.get("automatic_evidence", {}).get("provider_status", {}))
        securities.append({"symbol": symbol, "stages": deepcopy(current["financial_coverage"]["stages"]),
            "publication": deepcopy(base["publication"]), "independence": deepcopy(base["independence"]),
            "period_count": len(inputs.get("annual_periods", [])), "financial_source_status": deepcopy(inputs.get("financial_source_status"))})
        for model in base["models"]:
            paths = required_inputs(model["id"])
            fields = sorted({field for path in paths for field in path})
            candidate = details[model["id"]].get("candidate_input_sources", {})
            source_records = {field: deepcopy(record) for field, record in candidate.items()}
            incompatible = sorted(set(fields) & set(completeness.get("groups", {}).get("incompatible", [])))
            numeric_assumptions = {field: deepcopy(assumptions.get("metadata", {}).get(field, {})) for field in fields if field in MODEL_ASSUMPTIONS[model["id"]]}
            historic_model = old_models[model["id"]]
            compatible = financial_compatibility(inputs, values, paths, model["id"], incompatible, completeness["compatibility"])
            current_eligible = model["status"] == "valid" and model["eligibility"]["status"] not in {"ineligible", "unavailable"}
            publication = base.get("publication") or current["financial_coverage"].get("publication") or {}
            current_published = current_eligible and publication.get("result_type") == "current_eligible"
            rows.append({"symbol": symbol, "issuer_id": company.get("issuer_id"), "instrument_id": company.get("instrument_id"),
                "listing_id": company.get("listing_id"), "cik": company.get("cik"), "source_security_symbol": company.get("display_symbol", company["ticker"]),
                "identity_scope": "deterministic fixture registry UUIDs; not production database IDs", "security_form": company.get("security_form"),
                "business_category": company.get("issuer_business_category"), "reporting_framework": company.get("filing_regime", "unverified"),
                "model_id": model["id"], "method_family": next(group for group, members in GROUPS.items() if model["id"] in members),
                "required_inputs": paths, "available_inputs": [field for field in fields if values.get(field) is not None],
                "missing_inputs": deepcopy(model["eligibility"]["missing_inputs"]), "input_paths": deepcopy(model["eligibility"]["input_paths"]),
                "scope_incompatible_inputs": incompatible, "stale_or_expired_observations": deepcopy(stale),
                "required_assumptions": numeric_assumptions, "provider_restrictions": deepcopy(restrictions),
                "source_document_evidence": source_records, "financial_data_available": current["financial_coverage"]["stages"]["financial_statements"]["status"] == "available",
                "financial_data_compatible": compatible["compatible"], "financial_compatibility_assessment": compatible,
                "financial_reconciliations": deepcopy(inputs.get("financial_reconciliations", {})),
                "model_contract": {"applicability": CONTRACTS[model["id"]][0], "minimum_history_and_paths": CONTRACTS[model["id"]][1],
                    "assumptions_and_limits": CONTRACTS[model["id"]][2], "share_basis": "Verified selected instrument, currency, period and applicable class/split basis required",
                    "confidence": "Retain engine quality/warnings; family counts are not independent corroboration"},
                "economic_appropriateness": "ineligible" if model["eligibility"]["status"] == "ineligible" else "unverified" if "business_classification" in model["eligibility"]["missing_inputs"] else "not_excluded",
                "current_engine_status": model["status"], "recomputed_model_eligible": current_eligible,
                "current_model_eligible": current_published,
                "current_published": current_published, "current_fair_value": model["fair_value"] if current_published else None,
                "calculated_fair_value": model["fair_value"],
                "historical_replay_model_eligible": historic_model["status"] == "valid",
                "historical_replay_fair_value": historic_model["fair_value"], "historical_source_clock": source["as_of"],
                "publication_blockers": deepcopy(publication.get("blockers", [])), "publication_clocks": deepcopy(publication.get("clocks", {})),
                "result_type": "current_eligible" if current_published else "historical_illustration" if current_eligible and model["fair_value"] is not None else "unavailable",
                "blockers": deepcopy(model["eligibility"].get("blockers", [])), "warnings": deepcopy(model["warnings"])})
    return {"audit_version": "phase671-blockers-3", "population": population, "data_mode": source["data_mode"], "as_of": clock.isoformat(),
        "source_clock": source["as_of"], "security_denominator": len(records), "model_pair_denominator": len(rows),
        "historical_model_securities": len({row["symbol"] for row in rows if row["historical_replay_model_eligible"]}),
        "current_eligible_securities": len({row["symbol"] for row in rows if row["current_model_eligible"]}),
        "recomputed_eligible_securities": len({row["symbol"] for row in rows if row["recomputed_model_eligible"]}),
        "current_published_securities": len({row["symbol"] for row in rows if row["current_published"]}),
        "mocked_or_synthetic_results_included_in_real_coverage": False,
        "model_result_counts": dict(Counter(row["result_type"] for row in rows)), "blocker_ranking": rank_blockers(rows), "rows": rows,
        "securities": securities, "stages": {key: {"numerator": sum(row["stages"][key]["status"] == "available" for row in securities), "denominator": len(securities)} for key in securities[0]["stages"]},
        "limitations": ["Financial-source and listing-proof clocks remain independent.", "Sample denominators are not whole-market coverage.",
            "Historical eligibility is the dated source replay, never a current-publication assertion.", "Fixture omissions do not prove the full source lacks a financial concept."]}


def compare_reports(before, report):
    keys = ("population", "data_mode", "security_denominator", "model_pair_denominator", "source_clock")
    if any(before.get(key) != report[key] for key in keys):
        raise ValueError("Before/after comparisons require the same population, mode, source clock and denominators.")
    if instant(before["as_of"]) > instant(report["as_of"]):
        raise ValueError("Comparison cannot reverse the audit clock.")
    old = {(row["symbol"], row["model_id"]): row for row in before["rows"]}
    new = {(row["symbol"], row["model_id"]): row for row in report["rows"]}
    if len(old) != len(before["rows"]) or len(new) != len(report["rows"]) or old.keys() != new.keys():
        raise ValueError("Comparison requires the same unique security/model pairs.")
    return {"before_clock": before["as_of"], "changed_model_results": [
        {"symbol": symbol, "model_id": model, "before": old[(symbol, model)]["result_type"], "after": new[(symbol, model)]["result_type"]}
        for symbol, model in sorted(new) if new[(symbol, model)]["result_type"] != old[(symbol, model)]["result_type"]],
        "new_real_model_calculations": [{"symbol": symbol, "model_id": model} for symbol, model in sorted(new)
            if new[(symbol, model)].get("recomputed_model_eligible", new[(symbol, model)]["current_model_eligible"])
            and not old[(symbol, model)]["historical_replay_model_eligible"]
            and not old[(symbol, model)].get("recomputed_model_eligible", old[(symbol, model)]["current_model_eligible"])],
        "new_current_publications": [{"symbol": symbol, "model_id": model} for symbol, model in sorted(new)
            if new[(symbol, model)]["current_published"] and not old[(symbol, model)]["current_published"]]}


def markdown(report):
    lines = [f"# Phase 6.7.1 — {report['population']} evidence", "", f"Audit clock: {report['as_of']}; source replay clock: {report['source_clock']}.",
        f"Denominators: {report['security_denominator']} securities / {report['model_pair_denominator']} security-model pairs.", "",
        "| Security | Model | Current result | Historical eligible | Missing inputs | Blockers |", "| --- | --- | --- | --- | --- | --- |"]
    def cell(value):
        return str(value).replace("|", "&#124;").replace("\n", " ")
    for row in report["rows"]:
        lines.append("| " + " | ".join(map(cell, (row["symbol"], row["model_id"], row["result_type"], row["historical_replay_model_eligible"],
            ", ".join(row["missing_inputs"]), ", ".join(part["code"] for part in row["blockers"])))) + " |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--population", choices=("retained", "approved"), required=True)
    parser.add_argument("--as-of", required=True, help="Explicit zoned UTC/offset audit clock; source dates are never advanced.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown")
    parser.add_argument("--compare", help="Optional earlier JSON from the same population; modes/denominators must match.")
    parser.add_argument("--updated-evidence", help="Already acquired, authorized local manifest; no downloads or production imports.")
    parser.add_argument("--authorization-receipt", help="Expected question/receipt ID, checked against local manifest; caller must independently confirm consent.")
    args = parser.parse_args()
    def blocked(*_args, **_kwargs):
        raise RuntimeError("External HTTP is forbidden in Phase 6.7.1 replay.")
    async def async_blocked(*_args, **_kwargs):
        blocked()
    with patch.object(httpx.HTTPTransport, "handle_request", blocked), patch.object(httpx.AsyncHTTPTransport, "handle_async_request", async_blocked):
        captured = None
        inventory = None
        if args.updated_evidence:
            if not args.authorization_receipt:
                parser.error("--updated-evidence requires an explicit --authorization-receipt")
            inventory = load_local_evidence_manifest(args.updated_evidence, audit_clock=args.as_of,
                expected_authorization_question_id=args.authorization_receipt)
            captured = apply_local_updates(args.population, capture(args.population), inventory, instant(args.as_of))
        report = build_matrix(args.population, args.as_of, captured=captured)
        if inventory:
            report["additional_evidence"] = {"data_mode": "newly_approved_live", "application": "Isolated replay only; no production imports or refreshed financial facts",
                **{key: inventory[key] for key in ("contract_version", "authorization", "actual_requests", "actual_bytes", "limitations")},
                "sources": [{key: item[key] for key in ("provider", "endpoint", "symbol", "cik", "url", "http_status", "status", "bytes", "sha256", "retrieved_at", "source_summary") if key in item} for item in inventory["inventory"]]}
            report["limitations"].append("Base data_mode describes the frozen financial population; additional_evidence separately identifies authorized source updates.")
            report["limitations"].append("Updated replay applies reference and quote records only; validated profile/split/history inventory is not silently installed as financial evidence.")
    if args.compare:
        before = json.loads(Path(args.compare).read_text(encoding="utf-8"))
        report["comparison"] = compare_reports(before, report)
    Path(args.output).write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    if args.markdown:
        Path(args.markdown).write_text(markdown(report), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("population", "security_denominator", "model_pair_denominator", "historical_model_securities", "current_eligible_securities", "current_published_securities")}))


if __name__ == "__main__":
    main()
