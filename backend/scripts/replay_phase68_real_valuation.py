"""Explicit-clock, HTTP-blocked real SEC dividend scenario and import replay.

Default evidence is a small maintained public SEC excerpt. Full retained source
bytes may be selected with --sec-source/--sec-manifest. No mode acquires data,
connects to IBKR, imports an application database, or grants redistribution.
"""
import argparse
import asyncio
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
import math
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BACKEND), str(BACKEND / "tests"), str(BACKEND / "scripts")]

import httpx
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.core.database import Base, build_session_factory
from app.repositories.financial_repository import FinancialRepository
from app.services.dated_valuation_inputs import build_dated_inputs
from app.services.financial_import_service import apply_preview, build_preview
from app.services.financial_import_audit import load_approved_sec_source
from app.services.normalization import normalize_company_facts
from app.valuation.coverage import calculate_with_coverage
from app.valuation.inputs import build_valuation_inputs
from app.valuation.weighting import comparisons
from phase68_valuation_helpers import import_registry, real_fixture, retain_profile, request
import replay_phase671_valuation_coverage as previous


def instant(value):
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("An explicit zoned audit clock is required.")
    return result.astimezone(UTC)


@contextmanager
def offline(clock):
    def blocked(*_args, **_kwargs):
        raise RuntimeError("Phase 6.8 replay cannot perform provider requests.")
    async def async_blocked(*_args, **_kwargs):
        blocked()
    class AuditClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock.astimezone(tz) if tz else clock.replace(tzinfo=None)
    with patch.object(httpx.HTTPTransport, "handle_request", blocked), patch.object(httpx.AsyncHTTPTransport, "handle_async_request", async_blocked), \
            patch("app.registry.service.utcnow", return_value=clock), patch("app.valuation.engine.datetime", AuditClock), \
            patch("app.valuation.dated_intrinsic.datetime", AuditClock):
        yield


def _source(fixture, source, manifest, clock):
    if bool(source) != bool(manifest):
        raise ValueError("A retained full source and its exact acquisition manifest must be supplied together.")
    if source:
        raw, evidence = load_approved_sec_source(source, manifest)
        if instant(evidence["retrieved_at"]) > clock:
            raise ValueError("The original source acquisition cannot follow the audit clock.")
        if str(raw.get("cik")).zfill(10) != "0000789019":
            raise ValueError("This bounded first-valuation replay is scoped to the exact MSFT SEC issuer.")
        return raw, evidence, "previously_acquired_full_sec_companyfacts"
    return deepcopy(fixture["raw"]), deepcopy(fixture["source"]), "maintained_exact_public_sec_excerpt"


def _class_evidence(fixture):
    return {"source_type": "retained_sec_adapter_profile", "source_hash": fixture["profile"]["sha256"],
            "retrieved_at": fixture["profile"]["retrieved_at"], "ticker": "MSFT", "cik": "0000789019",
            "has_multiple_share_classes": False}


def _private_ibkr(observation, receipt=None, expected_identity=None, clock=None):
    # The local CLI retains an envelope, while adapters may supply a standalone
    # quote. Verify envelope scope before selecting the original hashed quote;
    # never merge its plan/history/account-shaped fields into the observation.
    if isinstance(observation, dict) and "schema_version" in observation:
        quote = observation.get("quote")
        scope = observation.get("scope")
        fields = ("issuer_id", "instrument_id", "listing_id", "cik", "ticker")
        if (observation.get("schema_version") != "fairworth-private-ibkr-1"
                or observation.get("provider") != "ibkr"
                or observation.get("permitted_use") != "personal_local_only"
                or observation.get("public_redistribution_allowed") is not False
                or observation.get("data_origin") != "actual_ibkr"
                or observation.get("source_retention") is not True
                or not isinstance(quote, dict) or not isinstance(scope, dict)
                or quote.get("data_origin") != observation["data_origin"]
                or not isinstance(quote.get("identity"), dict)
                or any(not scope.get(key) or scope[key] != quote["identity"].get(key) for key in fields)):
            raise ValueError("The retained local IBKR export has an unsupported format, permission or identity scope.")
        observation = quote
    if (not isinstance(observation, dict) or observation.get("provider") != "ibkr"
            or observation.get("permitted_use") != "personal_local_only"
            or observation.get("public_redistribution_allowed") is not False):
        raise ValueError("Only explicitly private IBKR observations may enter this local replay.")
    origin = observation.get("data_origin")
    if origin not in {"simulated_ibkr", "actual_ibkr"} or origin == "actual_ibkr" and not receipt:
        raise ValueError("Actual retained IBKR observations require a separate authorization receipt; simulated observations are never live tests.")
    if origin == "actual_ibkr":
        fingerprint = observation.get("observation_sha256")
        original = {key: value for key, value in observation.items() if key != "observation_sha256"}
        if fingerprint != hashlib.sha256(json.dumps(original, sort_keys=True).encode()).hexdigest():
            raise ValueError("The existing broker observation failed its original payload hash.")
    allowed = ("provider", "permitted_use", "public_redistribution_allowed", "data_origin", "price", "currency", "price_timestamp", "retrieved_at", "market_data_type")
    safe = {key: deepcopy(observation[key]) for key in allowed if key in observation}
    if (safe.get("currency") != "USD" or not safe.get("price_timestamp")
            or isinstance(safe.get("price"), bool) or not isinstance(safe.get("price"), (float, int))
            or not math.isfinite(safe["price"]) or safe["price"] <= 0
            or safe.get("market_data_type") not in {"live", "frozen", "delayed", "delayed_frozen"}):
        raise ValueError("The private observation requires an original source timestamp and compatible USD unit.")
    identity_fields = ("issuer_id", "instrument_id", "listing_id", "cik", "ticker")
    identity = {key: observation.get("identity", {}).get(key) for key in identity_fields}
    if identity.get("cik") != "0000789019" or identity.get("ticker") != "MSFT":
        raise ValueError("Private IBKR evidence cannot be transferred to a different issuer or symbol.")
    if expected_identity is not None and any(not identity.get(key) or identity[key] != expected_identity.get(key) for key in identity_fields):
        raise ValueError("The private broker observation does not match the exact selected issuer, instrument and listing.")
    observed, retrieved = instant(safe["price_timestamp"]), instant(safe.get("retrieved_at"))
    if observed > retrieved or clock is not None and retrieved > clock:
        raise ValueError("The broker source and retrieval clocks are incompatible with this audit.")
    contract_fields = ("con_id", "symbol", "local_symbol", "security_type", "exchange", "primary_exchange", "currency", "trading_class", "time_zone_id")
    contract = {key: observation.get("source_security", {}).get(key) for key in contract_fields}
    if origin == "actual_ibkr" and (contract.get("symbol") != "MSFT" or contract.get("local_symbol") != "MSFT"
            or contract.get("currency") != "USD" or contract.get("security_type") != "STK"
            or contract.get("primary_exchange") not in {"NASDAQ", "ISLAND"} or contract.get("trading_class") != "MSFT"
            or not isinstance(contract.get("con_id"), int) or isinstance(contract["con_id"], bool) or contract["con_id"] <= 0):
        raise ValueError("The actual retained broker contract has incompatible instrument metadata.")
    safe["identity"], safe["source_security"] = identity, contract
    safe["authorization_receipt"] = receipt if origin == "actual_ibkr" else None
    return safe


def _published_api(factory, registry, selected):
    """Exercise the ordinary FastAPI response contract after a local import."""
    from fastapi import FastAPI
    from app.api.routes.valuation import router
    from app.core.config import Settings
    from app.services.valuation_service import ValuationService
    from app.valuation.schemas import ValuationResponse
    settings = Settings(_env_file=None)
    service = ValuationService(SimpleNamespace(registry=registry), SimpleNamespace(repository=FinancialRepository(factory)), settings)
    application = FastAPI()
    application.include_router(router, prefix="/api")
    application.state.valuation_service = service
    async def publish():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://offline-test") as client:
            return await client.post("/api/stocks/MSFT/valuation/calculate", json=request(evidence_as_of=selected).model_dump(mode="json"))
    response = asyncio.run(publish())
    if response.status_code != 200:
        raise ValueError("The normal FastAPI valuation response failed after the isolated import.")
    parsed = ValuationResponse.model_validate(response.json())
    return {"status_code": response.status_code, "response_schema_valid": True,
        "intrinsic_value": parsed.scenarios["base"].intrinsic["value"],
        "classification": parsed.scenarios["base"].summary.classification,
        "publication_type": parsed.scenarios["base"].publication["result_type"],
        "market_comparison": parsed.scenarios["base"].market_comparison["status"],
        "external_http_calls": 0}


def replay(mode, as_of, *, evidence_as_of=None, sec_source=None, sec_manifest=None,
           import_batch_id=None, ibkr_observation=None, ibkr_receipt=None):
    clock = instant(as_of)
    fixture = real_fixture()
    selected = evidence_as_of or fixture["evidence_as_of"]
    if instant(selected) > clock:
        raise ValueError("The selected evidence clock cannot follow the actual audit calculation clock.")
    with offline(clock):
        if mode == "baseline":
            captured = previous.capture("retained")
            baseline = previous.build_matrix("retained", as_of, captured=captured)
            return {"phase": "6.8", "mode": mode, "as_of": clock.isoformat(), "data_mode": "phase672_retained_baseline",
                    "security_denominator": baseline["security_denominator"], "model_pair_denominator": baseline["model_pair_denominator"],
                    "historical_regressions": {symbol: records[1]["scenarios"]["base"]["summary"]["fair_value"]
                                               for symbol, records in captured[1].items() if symbol in {"AAPL", "MSFT"}},
                    "current_published_securities": baseline["current_published_securities"],
                    "baseline": baseline, "application_writes": 0, "live_provider_requests": 0}
        raw, source, source_mode = _source(fixture, sec_source, sec_manifest, clock)
        test_import = None
        engine = None
        if mode in {"approved-import", "actual-ibkr"}:
            if not import_batch_id:
                raise ValueError("An exact existing approved application import batch ID is required.")
            from app.core.config import Settings
            settings = Settings()
            engine = create_engine(settings.database_url, pool_pre_ping=True)
            factory = build_session_factory(engine)
            from app.registry.service import SecurityRegistryService
            registry = SecurityRegistryService(factory, settings)
            inputs = build_dated_inputs(registry, FinancialRepository(factory), settings, "MSFT")
            if inputs["financial_import"]["import_batch_id"] != import_batch_id:
                raise ValueError("The selected application snapshot does not belong to that reviewed import batch.")
            source = deepcopy(inputs["financial_import"])
            source_mode = "existing_approved_application_import_read_only"
        else:
            engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
            Base.metadata.create_all(engine)
            factory = build_session_factory(engine)
            registry = import_registry(factory, fixture)
            retain_profile(factory, fixture)
            if mode == "test-import":
                with TemporaryDirectory(prefix="fairworth-phase68-test-import-") as temporary:
                    path = Path(temporary) / "MSFT.json"
                    manifest = Path(temporary) / "manifest.json"
                    data = json.dumps(raw, sort_keys=True).encode()
                    path.write_bytes(data)
                    manifest.write_text(json.dumps({"attempts": [{"file": path.name, "status": "received", "http_status": 200,
                        "cik": "0000789019", "url": source.get("url", source.get("source_url")), "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(), "retrieved_at": source["retrieved_at"]}]}))
                    plan = build_preview(engine, [{"source": str(path), "manifest": str(manifest), "ticker": "MSFT"}],
                                         as_of=clock, sec_cache_ttl_seconds=21600)
                    applied = apply_preview(engine, plan, confirmation=f"APPLY {plan['preview_digest']}")
                    repeated = apply_preview(engine, plan, confirmation=f"APPLY {plan['preview_digest']}")
                    test_import = {"database": "disposable_in_memory_sqlite", "preview_totals": plan["totals"],
                                   "row_changes": applied["row_changes"], "repeat_already_applied": repeated["already_applied"],
                                   "source_retention": "Exact excerpt/full-source values serialized to a temporary test-only source; original acquired document provenance is reported separately."}
                inputs = build_dated_inputs(registry, FinancialRepository(factory), SimpleNamespace(sec_cache_ttl_seconds=21600), "MSFT")
            else:
                identity = registry._with_freshness(registry.repository.resolve("MSFT"))
                company = {**fixture["profile"]["payload"], **identity}
                inputs = build_valuation_inputs({"company": company, "market": None}, normalize_company_facts(raw, cik=company["cik"]), source["retrieved_at"])
                inputs["dated_share_basis_evidence"] = _class_evidence(fixture)
                inputs["financial_source_status"] = {"status": "stale"}
        try:
            default = calculate_with_coverage(inputs)
            result = calculate_with_coverage(inputs, request(evidence_as_of=selected))
            base = result["scenarios"]["base"]
            intrinsic = base["intrinsic"]
            assisted = intrinsic["status"] == "available" and intrinsic["workflow"] == "user_assisted"
            current = base["publication"]["current_eligible"]
            report = {"phase": "6.8", "mode": mode, "as_of": clock.isoformat(), "evidence_as_of": instant(selected).isoformat(),
                "data_mode": source_mode, "source": source, "security_denominator": 1, "model_pair_denominator": 11,
                "identity": {key: inputs["company"].get(key) for key in ("ticker", "cik", "issuer_id", "instrument_id", "listing_id", "exchange", "security_form")},
                "coverage": {"financial_statements_available": 1, "financial_data_imported_into_application": int(mode in {"approved-import", "actual-ibkr"}),
                    "financial_data_imported_into_test_database": int(mode == "test-import"), "compatible_financial_evidence": int(inputs["basis"]["share_basis_verified"]),
                    "automatic_default_model_eligible": int(default["scenarios"]["base"]["summary"]["count"] > 0),
                    "user_assisted_model_eligible": int(assisted), "historical_real_data_intrinsic_estimate": int(assisted and not current),
                    "current_intrinsic_under_reviewed_policy": int(current), "compatible_current_market_comparison": 0,
                    "two_corroborating_model_families": 0},
                "intrinsic": intrinsic, "market_comparison": base["market_comparison"], "publication": base["publication"],
                "model": next(model for model in base["models"] if model["id"] == "dividend"), "independence": base["independence"],
                "test_database_import": test_import, "application_writes": 0, "live_provider_requests": 0,
                "limitations": ["Only one selected security is measured. No registry-wide financial coverage is inferred.",
                    "The dividend discount scenario capitalizes declared common cash dividends with explicit analyst-entered payout/growth/return assumptions; repurchases and payout changes are excluded.",
                    "The selected evidence clock dates archived identity support. It is neither the financial observation date nor today's listing verification.",
                    "No original AAPL/MSFT historical regression is relabeled as a new current default valuation.",
                    "A test database import is not a separately authorized application database import."]}
            if mode in {"test-import", "approved-import", "actual-ibkr"}:
                report["published_api_response"] = _published_api(factory, registry, selected)
                if report["published_api_response"]["intrinsic_value"] != intrinsic["value"]:
                    raise ValueError("The published API intrinsic result diverged from the deterministic replay.")
            if mode in {"mock-ibkr", "actual-ibkr"}:
                if ibkr_observation:
                    observed = json.loads(Path(ibkr_observation).read_text(encoding="utf-8"))
                elif mode == "mock-ibkr":
                    observed = {"provider": "ibkr", "permitted_use": "personal_local_only", "public_redistribution_allowed": False,
                        "data_origin": "simulated_ibkr", "price": 100.0, "currency": "USD", "price_timestamp": clock.isoformat(),
                        "retrieved_at": clock.isoformat(), "market_data_type": "delayed", "identity": report["identity"]}
                else:
                    raise ValueError("Actual IBKR replay accepts only an existing local authorized observation; it cannot connect to a broker.")
                private = _private_ibkr(observed, ibkr_receipt, report["identity"], clock)
                if mode == "mock-ibkr" and private["data_origin"] != "simulated_ibkr":
                    raise ValueError("A real subscription observation cannot be mixed into the mock population.")
                if mode == "actual-ibkr" and private["data_origin"] != "actual_ibkr":
                    raise ValueError("Simulated IBKR data cannot be counted as an actual broker observation.")
                report["private_market_population"] = {"denominator": 1, "data_mode": private["data_origin"], "observation": private,
                    "comparison": comparisons(intrinsic["value"], private.get("price")),
                    "limitations": ["Private local comparison only; excluded from the real SEC-only coverage denominator and every public API response.",
                                    "Delayed or frozen observations are never described as live. No IBKR connection occurred in replay."]}
            return report
        finally:
            if engine is not None:
                engine.dispose()


def markdown(report):
    if report["mode"] == "baseline":
        return previous.markdown(report["baseline"])
    intrinsic = report["intrinsic"]
    lines = ["# Phase 6.8 real-financial-evidence replay", "", f"Mode: `{report['mode']}`; source: `{report['data_mode']}`.", "",
             f"Calculation clock: {report['as_of']}; archived identity evidence clock: {report['evidence_as_of']}.", "",
             f"MSFT dividend-discount scenario: **{intrinsic['value']:.2f} USD/common share**; financial observation: {intrinsic['financial_observation_date']}.", "",
             "| Coverage stage | Securities / 1 |", "| --- | --- |"]
    lines += [f"| {key.replace('_', ' ')} | {value} |" for key, value in report["coverage"].items()]
    lines += ["", "Source accessions: " + ", ".join(intrinsic["source_identifiers"]), "",
              "Application writes: 0. Live provider requests: 0.", ""]
    lines += ["- " + item for item in report["limitations"] + intrinsic["limitations"]]
    if report.get("private_market_population"):
        lines += ["", "Private broker evidence is a separate local-only population and must not be publicly redistributed."]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=("baseline", "retained-sec", "test-import", "approved-import", "mock-ibkr", "actual-ibkr"))
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--evidence-as-of")
    parser.add_argument("--sec-source", type=Path)
    parser.add_argument("--sec-manifest", type=Path)
    parser.add_argument("--import-batch-id")
    parser.add_argument("--ibkr-observation", type=Path)
    parser.add_argument("--ibkr-authorization-receipt")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args()
    if args.mode in {"mock-ibkr", "actual-ibkr"}:
        workspace = BACKEND.parent.resolve()
        allowed = workspace / ".phase68.local"
        for path in (args.output, args.markdown):
            if path is not None and not path.resolve().is_relative_to(allowed):
                raise ValueError("Private IBKR replay output is restricted to ignored .phase68.local/.")
    report = replay(args.mode, args.as_of, evidence_as_of=args.evidence_as_of, sec_source=args.sec_source,
        sec_manifest=args.sec_manifest, import_batch_id=args.import_batch_id, ibkr_observation=args.ibkr_observation,
        ibkr_receipt=args.ibkr_authorization_receipt)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, default=str, allow_nan=False) + "\n", encoding="utf-8")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(markdown(report), encoding="utf-8")
    print(json.dumps({"mode": report["mode"], "application_writes": 0, "live_provider_requests": 0,
                      "coverage": report.get("coverage"), "historical_regressions": report.get("historical_regressions")}))


if __name__ == "__main__":
    main()
