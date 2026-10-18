"""Replay approved identity excerpts and retained financials, never providers."""
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
from types import SimpleNamespace

from app.registry.repository import SecurityRegistryRepository
from app.services.coverage_service import CoverageService
from app.valuation.engine import calculate_valuation
from app.valuation.inputs import build_valuation_inputs
from test_ai_evidence_context import retained_inputs

FIXTURES = Path(__file__).parent / "fixtures/registry"


async def replay_reference_sample(session_factory):
    fixture = json.loads((FIXTURES / "sec_reference_sample_2026_10_18.json").read_text(encoding="utf-8"))
    jpm = json.loads((FIXTURES / "jpm_retained_annual_excerpt.json").read_text(encoding="utf-8"))
    repository = SecurityRegistryRepository(session_factory)
    records = [record for sample in fixture["samples"] for record in sample["directory_records"]]
    repository.import_snapshot(records, {"source": "sec-edgar-reference-sample", "as_of": fixture["as_of"][:10],
                                "scope": fixture["description"], "rights": "Public SEC reference excerpt; observe SEC fair-access policy.",
                                "source_url": fixture["directory_provenance"]["url"]})
    samples = []
    for row in fixture["samples"]:
        symbol = row["requested_symbol"]
        selected = repository.resolve(symbol)
        data = row.get("submissions") or {}
        company = {**selected, "industry": data.get("sicDescription"), "sic": data.get("sic")}
        if symbol in retained_inputs():
            inputs = deepcopy(retained_inputs()[symbol])
            assert inputs["company"]["cik"] == company["cik"]
            inputs["company"].update(company)
        elif symbol == "JPM":
            inputs = build_valuation_inputs({"company": {**jpm["profile"]["company"], **company}}, jpm["normalized"], jpm["source"]["retrieved_at"])
        else:
            inputs = build_valuation_inputs({"company": company}, {"currency": None, "annual": [], "quarterly": [], "warnings": []})
        inputs["data_status"] = "stale" if inputs.get("annual_periods") else "partial"
        class Companies:
            async def company_identity(self, _ticker, _instrument_id=None):
                return company, None
        class Valuations:
            async def inputs(self, _ticker, **_scope):
                return deepcopy(inputs)
            async def calculate(self, _ticker, **_scope):
                return calculate_valuation(deepcopy(inputs))
        coverage = await CoverageService(Companies(), None, Valuations(), SimpleNamespace(status=lambda: {})).coverage(symbol)
        samples.append({"requested_symbol": symbol, "data_mode": "retained_public", "sector": data.get("sicDescription"), "coverage": coverage})
    return {"data_mode": "retained_public", "as_of": datetime.now().astimezone().isoformat(), "samples": samples}
