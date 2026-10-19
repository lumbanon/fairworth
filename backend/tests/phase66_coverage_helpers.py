"""Replay actual dated listing excerpts and retained financials, never providers."""
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.registry.repository import SecurityRegistryRepository
from app.registry.service import SecurityRegistryService
from app.services.coverage_service import CoverageService
from app.valuation.engine import calculate_valuation
from app.valuation.inputs import build_valuation_inputs
from test_ai_evidence_context import retained_inputs

FIXTURES = Path(__file__).parent / "fixtures/registry"


def captured_listings():
    return json.loads((FIXTURES / "nasdaq_listing_sample_2026_10_19.json").read_text(encoding="utf-8"))


def import_captured_listings(factory):
    fixture = captured_listings()
    repository = SecurityRegistryRepository(factory)
    refs = [item for sample in fixture["samples"] for item in sample["sec_reference_records"]]
    refs += fixture["unlinked_sec_reference_records"]
    refs = list({json.dumps(item, sort_keys=True): item for item in refs}.values())
    provenance = {**fixture["sec_reference_provenance"], "complete_scope": False,
                  "scope": "Curated actual SEC reference excerpts; no whole-market completeness assertion."}
    repository.import_snapshot(refs, provenance)
    original = {item["ticker"]: repository.resolve(item["ticker"]) for item in refs}
    for source in fixture["sources"]:
        records = [sample["listing_record"] for sample in fixture["samples"]
                   if any(ref.get("url") == source["source_url"] for ref in sample["listing_record"]["source_refs"])]
        repository.import_snapshot(records, {**source, "complete_scope": False,
            "scope": "Curated actual directory excerpts; original source metadata describes the full acquired file."})
    return fixture, repository, original


async def replay_verified_sample(factory):
    fixture, repository, _ = import_captured_listings(factory)
    as_of = datetime.fromisoformat(fixture["audit_as_of"])
    metadata_fixture = json.loads((FIXTURES / "sec_reference_sample_2026_10_18.json").read_text())
    metadata = {row["requested_symbol"]: row.get("submissions") or {} for row in metadata_fixture["samples"]}
    jpm = json.loads((FIXTURES / "jpm_retained_annual_excerpt.json").read_text())
    registry = SecurityRegistryService(factory, SimpleNamespace(registry_bootstrap_enabled=False, registry_cache_ttl_seconds=86400))
    samples = []
    # An explicitly dated replay must not acquire a new "current" identity on
    # each test run. These clocks are test harness injection, never production.
    with patch("app.registry.service.utcnow", return_value=as_of), patch("app.services.coverage_service.utcnow", return_value=as_of):
        for sample in fixture["samples"]:
            symbol, record = sample["requested_symbol"], sample["listing_record"]
            matches = [item for item in repository.search(symbol, 50)["results"]
                       if item["listing_verification"].get("record_hash") == record["source_record_hash"]]
            if len(matches) != 1:
                raise ValueError("The captured listing no longer resolves uniquely to its exact source record.")
            raw = matches[0]
            company = await registry.resolve(raw["ticker"], raw["instrument_id"], raw["listing_id"])
            details = metadata.get(symbol, {})
            sic = str(details.get("sic") or "")
            if sic:
                bank = sic in {"6021", "6022", "6029", "6035", "6036", "6061", "6062", "6081", "6082", "6099"}
                reit = sic == "6798"
                company.update(sic=sic, industry=details.get("sicDescription"), is_bank=bank, is_reit=reit)
                company["issuer_business_category"] = "bank" if bank else "reit" if reit else "insurance" if 6300 <= int(sic) <= 6399 else "other" if 6000 <= int(sic) <= 6999 else "operating_company"
                company["issuer_classification_evidence"] = {"provider": "sec-edgar", "concept": "sic", "value": sic, "as_of": "2026-10-18"}
            if symbol in retained_inputs():
                inputs = deepcopy(retained_inputs()[symbol])
                if inputs["company"]["cik"] != company["cik"]:
                    raise ValueError("Retained financial evidence does not match the selected issuer.")
                inputs["company"].update(company)
            elif symbol == "JPM":
                if company["cik"] != jpm["profile"]["company"]["cik"]:
                    raise ValueError("Retained financial evidence does not match the selected issuer.")
                inputs = build_valuation_inputs({"company": {**jpm["profile"]["company"], **company}}, jpm["normalized"], jpm["source"]["retrieved_at"])
            else:
                inputs = build_valuation_inputs({"company": company}, {"currency": None, "annual": [], "quarterly": [], "warnings": []})
            inputs["data_status"] = "stale" if inputs.get("annual_periods") else "partial"
            class Companies:
                async def company_identity(self, _ticker, **_scope):
                    return company, None
            class Valuations:
                async def inputs(self, _ticker, **_scope):
                    return deepcopy(inputs)
                async def calculate(self, _ticker, **_scope):
                    return calculate_valuation(deepcopy(inputs))
            valuation = calculate_valuation(deepcopy(inputs))
            summary = valuation["scenarios"]["base"]["summary"]
            coverage = await CoverageService(Companies(), None, Valuations(), SimpleNamespace(status=lambda: {})).coverage(company["ticker"])
            samples.append({"requested_symbol": symbol, "data_mode": "real_verified", "financial_data_mode": "retained_public",
                "financial_source_dates": {"reporting_period": inputs.get("reporting_period"), "retrieved_at": inputs.get("financial_retrieved_at")},
                "retained_default_fair_value": summary.get("fair_value"), "retained_default_classification": summary.get("classification"),
                "coverage": coverage})
    return {"data_mode": "real_verified", "as_of": as_of.isoformat(), "samples": samples}
