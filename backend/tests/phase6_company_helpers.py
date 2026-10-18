"""Reproducible, offline company audit using maintained dated public excerpts.

The overlay adds only compatible non-null observations. It is a regression
fixture assembler, not a provider adapter, and never supplies valuation policy
or fills unknown financial fields merely to increase model coverage.
"""

from copy import deepcopy
import json
from pathlib import Path


FIXTURES = Path(__file__).parent / "fixtures" / "valuation"
COMPANIES = ("AAPL", "MSFT", "NVDA", "ORCL")


def source_examples():
    statements = json.loads((FIXTURES / "verified_provider_excerpts.json").read_text(encoding="utf-8"))["companies"]
    automatic = json.loads((FIXTURES / "automatic_evidence_excerpts.json").read_text(encoding="utf-8"))["companies"]
    additions = json.loads((FIXTURES / "phase6_provider_excerpts.json").read_text(encoding="utf-8"))["companies"]
    return statements, automatic, additions


def phase6_company_inputs(ticker):
    from app.services.normalization import (
        NORMALIZATION_VERSION, complete_conventional_debt_provenance, normalize_company_facts,
    )
    from app.valuation.automatic import prepare_automatic_inputs
    from app.valuation.inputs import build_valuation_inputs

    statements, automatic, additions = source_examples()
    original, extra = statements[ticker], additions[ticker]
    normalized = deepcopy(original["normalized"])
    original_period = max(normalized["annual"], key=lambda period: period["end_date"])
    additional = normalize_company_facts(extra["companyfacts_excerpt"])["annual"]
    selected = [period for period in additional if all(period[key] == original_period[key] for key in
                                                      ("fiscal_year", "fiscal_period", "start_date", "end_date", "currency"))]
    if len(selected) != 1:
        raise ValueError("A source excerpt must match exactly one original fiscal duration and reporting currency.")
    extra_period = selected[0]
    added = []
    for field, value in extra_period["metrics"].items():
        if value is None:
            continue  # An absent excerpt observation never erases an old fact.
        existing = original_period["metrics"].get(field)
        if existing is not None and existing != value:
            raise ValueError(f"Conflicting dated source observation for {ticker} {field}; no silent replacement is permitted.")
        if existing is None:
            original_period["metrics"][field] = value
            original_period["provenance"][field] = deepcopy(extra_period["provenance"][field])
            for observation in original_period["provenance"][field]:
                observation["retrieved_at"] = extra["retrieved_at"]
            added.append(field)
    quarantined = []
    for field in ("short_term_debt", "total_debt"):
        records = original_period["provenance"].get(field, [])
        valid = (records and all(record.get("concept") == "ShortTermBorrowings" for record in records)
                 if field == "short_term_debt" else
                 complete_conventional_debt_provenance(records, end_date=original_period["end_date"]))
        if original_period["metrics"].get(field) is not None and not valid:
            original_period["metrics"][field] = None
            original_period["provenance"].pop(field, None)
            quarantined.append(field)
            warning = {"field": field, "code": "incomplete_conventional_debt_scope",
                       "message": "Historical partial borrowing or lease-inclusive current debt does not establish complete conventional financial debt; its dated original is preserved in the maintained source fixture."}
            original_period.setdefault("warnings", []).append(warning)
            normalized.setdefault("warnings", []).append(warning)
    normalized["normalization_version"] = NORMALIZATION_VERSION
    inputs = build_valuation_inputs(original["profile"], normalized, original["retrieved_at"])
    for period in inputs["annual_periods"]:
        if period["end_date"] == original_period["end_date"]:
            for field in added:
                if field in period["facts"]:
                    period["facts"][field]["retrieved_at"] = extra["retrieved_at"]
    for field in added:
        if field in inputs["facts"]:
            inputs["facts"][field]["retrieved_at"] = extra["retrieved_at"]
    evidence = deepcopy(automatic[ticker]["evidence"])
    prepared = prepare_automatic_inputs(inputs, evidence)
    return prepared, evidence, {
        "original_financial_retrieved_at": original["retrieved_at"],
        "additional_financial_retrieved_at": extra["retrieved_at"],
        "additional_source_url": extra["source_url"],
        "additional_period": extra["selected_period"],
        "added_fields": sorted(added), "quarantined_legacy_fields": quarantined,
        "limitations": ["The original quote and automatic-assumption excerpts remain dated observations.",
                        "Additional financial fields do not establish additional independent valuation models."],
    }


def comparison_snapshot(inputs, evidence, result):
    """A small audit shape shared by baseline and current engine subprocesses."""
    base = result["scenarios"]["base"]
    summary, assumptions = base["summary"], base["assumptions"].get("metadata", {})
    quote = result["market"]
    return {
        "engine_version": result["engine_version"],
        "assumption_methodology_version": result.get("assumption_methodology_version"),
        "reporting_period": inputs.get("reporting_period"),
        "financial_retrieved_at": inputs.get("financial_retrieved_at"),
        "automatic_as_of_date": evidence.get("as_of_date"),
        "quote": {key: quote.get(key) for key in ("price", "price_timestamp", "retrieved_at", "currency", "provider", "status", "source_type")},
        "provider_status": evidence.get("provider_status", {}),
        "fair_value": summary["fair_value"], "contributing_count": summary["count"],
        "effective_weights": summary["effective_weights"], "classification": summary["classification"],
        "confidence": base["confidence"],
        "models": [{
            "id": model["id"], "name": model["name"], "status": model["status"],
            "eligibility_status": model["eligibility"]["status"], "fair_value": model["fair_value"],
            "effective_weight": summary["effective_weights"].get(model["id"]),
            "classification": model["classification"], "source_quality": model["source_quality"],
            "missing_inputs": model["eligibility"].get("missing_inputs", []),
            "reason_codes": model["eligibility"].get("reason_codes", []),
            "reason": model["eligibility"]["reason"], "warnings": model["warnings"],
            "used_assumptions": {field: {key: assumptions[field].get(key) for key in (
                "value", "unit", "source_type", "source_category", "evidence_type", "observation_date",
                "financial_period", "source_identifiers", "dependency_fields", "policy_dependencies",
                "derivation_formula", "overridden",
            )} for field in model["source_quality"].get("used_inputs", []) if field in assumptions},
        } for model in base["models"]],
    }


def write_comparison_report():
    """Compare the committed Phase 5.1 code with current code, entirely offline.

    Run from the repository: backend/.venv/Scripts/python.exe
    backend/tests/phase6_company_helpers.py. The export/report are ignored local
    diagnostics; the dated input fixtures and this assembler are maintained.
    """
    import io
    import subprocess
    import sys
    import zipfile

    root = Path(__file__).resolve().parents[2]
    baseline_commit = "4a4eb874abd0a0a45bc83d6b1cfb6ddc9236f516"
    output = root / ".phase6.local"
    output.mkdir(exist_ok=True)
    exported = output / ("baseline-source-" + baseline_commit[:12])
    exported.mkdir(exist_ok=True)
    archive = subprocess.run(["git", "archive", "--format=zip", baseline_commit, "backend/app"],
                             cwd=root, capture_output=True, check=True)
    with zipfile.ZipFile(io.BytesIO(archive.stdout)) as source:
        for member in source.infolist():
            target = (exported / member.filename).resolve()
            if not target.is_relative_to(exported.resolve()):
                raise ValueError("The baseline archive contains an invalid path.")
        source.extractall(exported)
    baseline_script = """
import json, sys
sys.path[:0] = sys.argv[1:3]
import httpx
def deny_http(*args, **kwargs):
    raise AssertionError('The company audit is offline; external HTTP is forbidden.')
async def deny_async_http(*args, **kwargs):
    raise AssertionError('The company audit is offline; external HTTP is forbidden.')
httpx.HTTPTransport.handle_request = deny_http
httpx.AsyncHTTPTransport.handle_async_request = deny_async_http
from phase6_company_helpers import source_examples, comparison_snapshot
from app.valuation.inputs import build_valuation_inputs
from app.valuation.automatic import prepare_automatic_inputs
from app.valuation.engine import calculate_valuation
statements, automatic, _ = source_examples()
results = {}
for ticker, original in statements.items():
    evidence = automatic[ticker]['evidence']
    inputs = prepare_automatic_inputs(build_valuation_inputs(original['profile'], original['normalized'], original['retrieved_at']), evidence)
    results[ticker] = comparison_snapshot(inputs, evidence, calculate_valuation(inputs))
print(json.dumps(results, allow_nan=False))
"""
    baseline_run = subprocess.run([sys.executable, "-c", baseline_script, str(exported / "backend"), str(Path(__file__).parent)],
                                  cwd=root, capture_output=True, text=True, encoding="utf-8", check=True)
    before = json.loads(baseline_run.stdout)
    sys.path.insert(0, str(root / "backend"))
    from app.valuation.engine import calculate_valuation
    import httpx
    def deny_http(*args, **kwargs):
        raise AssertionError("The company audit is offline; external HTTP is forbidden.")
    async def deny_async_http(*args, **kwargs):
        raise AssertionError("The company audit is offline; external HTTP is forbidden.")
    # This function is a standalone audit command, not imported test setup.
    # Block concrete transports in both the baseline and current processes.
    httpx.HTTPTransport.handle_request = deny_http
    httpx.AsyncHTTPTransport.handle_async_request = deny_async_http
    report = {"baseline_commit": baseline_commit,
              "source_mode": "maintained_dated_public_fixtures_with_compatible_phase6_excerpts",
              "live_provider_requests": 0, "openai_requests": 0,
              "limitations": ["Quotes are dated provider observations, never current-price claims.",
                              "The baseline uses committed Phase 5.1 code; the after result uses current code and only compatible excerpt additions.",
                              "No missing debt, D&A, working-capital, preferred-equity or financing scope is supplied from unsupported subtotals."],
              "companies": {}}
    for ticker in COMPANIES:
        inputs, evidence, overlay = phase6_company_inputs(ticker)
        after = comparison_snapshot(inputs, evidence, calculate_valuation(inputs))
        report["companies"][ticker] = {"before": before[ticker], "after": after, "source_overlay": overlay,
                                        "fair_value_changed": before[ticker]["fair_value"] != after["fair_value"],
                                        "contributing_count_changed": before[ticker]["contributing_count"] != after["contributing_count"]}
    path = output / "four-company-comparison.json"
    path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    print(write_comparison_report())
