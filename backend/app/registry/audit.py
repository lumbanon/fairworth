"""Summarize saved coverage responses without provider or AI access."""
import argparse
from collections import Counter
from datetime import datetime
from html import escape
import json
from pathlib import Path

from app.registry.repository import _public_reference
from app.schemas.coverage import CoverageResponse
from app.services.coverage_service import RESTRICTED

STAGES = tuple(CoverageResponse.model_fields["stages"].annotation.model_fields)


def summarize(bundle):
    _public_reference(bundle)
    mode = bundle.get("data_mode")
    if mode not in {"retained_public", "mocked"}:
        raise ValueError("An explicit retained_public or mocked data mode is required.")
    as_of = datetime.fromisoformat(bundle["as_of"].replace("Z", "+00:00"))
    if as_of.tzinfo is None:
        raise ValueError("The audit as-of date must include a timezone.")
    samples = bundle.get("samples")
    if not isinstance(samples, list) or not samples or len(samples) > 10000:
        raise ValueError("An audit requires a bounded, non-empty sample.")
    rows, seen = [], set()
    for sample in samples:
        if sample.get("data_mode") != mode:
            raise ValueError("Real and mocked samples must be audited separately.")
        coverage = CoverageResponse.model_validate(sample["coverage"]).model_dump(mode="json")
        identity = coverage["identity"] or {}
        symbol = str(sample["requested_symbol"]).strip().upper()
        key = identity.get("listing_id") or identity.get("instrument_id") or symbol
        if key in seen:
            raise ValueError("Duplicate sampled security would inflate the audit denominator.")
        seen.add(key)
        observed_at = datetime.fromisoformat(coverage["as_of"].replace("Z", "+00:00"))
        if observed_at.tzinfo is None:
            raise ValueError("Each sampled as-of date must include a timezone.")
        if observed_at > as_of:
            raise ValueError("The audit as-of date precedes a sampled observation.")
        valuation = coverage["stages"]["valuation"]
        count = valuation.get("contributing_model_count")
        if count is not None and (type(count) is not int or count < 0 or count > 11):
            raise ValueError("Contributing count must be an exact bounded engine count or null.")
        stages = coverage["stages"]
        restrictions = [{"stage": name, "codes": sorted(set(value.get("reason_codes", [])) & RESTRICTED
                         | set(value.get("provider_restrictions", [])) & RESTRICTED)}
                        for name, value in stages.items()]
        restrictions = [item for item in restrictions if item["codes"]]
        blockers = [{"stage": name, "status": value["status"], "reason": value["reason"],
                     "codes": value.get("reason_codes", [])}
                    for name, value in stages.items() if value["status"] != "available"]
        rows.append({"requested_symbol": symbol, "identity": identity or None,
                     "issuer": identity.get("issuer_id") or identity.get("cik") or "unresolved",
                     "exchange": identity.get("exchange") or "unverified",
                     "sector": sample.get("sector") or "unverified",
                     "instrument_type": identity.get("instrument_type") or "unverified",
                     "as_of": coverage["as_of"], "methodology_version": coverage["methodology_version"],
                     "stages": coverage["stages"], "contributing_model_count": count,
                     "eligible_models": valuation.get("eligible_models"),
                     "valuation_quality": valuation.get("quality"), "valuation_confidence": valuation.get("confidence"),
                     "provider_restrictions": restrictions, "unresolved_blockers": blockers,
                     "ai_evidence_available": coverage["stages"]["ai_research"].get("evidence_available"),
                     "ai_provider_ready": coverage["stages"]["ai_research"].get("provider_ready"),
                     "generated_report": "not_audited"})
    rows.sort(key=lambda row: (row["requested_symbol"], str(row["identity"])))
    groups = {}
    for dimension in ("issuer", "exchange", "sector", "instrument_type"):
        grouped = {}
        for value in sorted({row[dimension] for row in rows}):
            subset = [row for row in rows if row[dimension] == value]
            grouped[value] = {"sample_denominator": len(subset), "stage_status_counts": {
                name: dict(sorted(Counter(row["stages"][name]["status"] for row in subset).items())) for name in STAGES}}
        groups[dimension] = grouped
    return {"audit_version": "coverage-sample-audit-1", "as_of": as_of.isoformat(), "data_mode": mode,
            "sample_denominator": len(rows), "unique_issuer_denominator": len({row["issuer"] for row in rows if row["issuer"] != "unresolved"}),
            "stage_status_counts": {name: dict(sorted(Counter(row["stages"][name]["status"] for row in rows).items())) for name in STAGES},
            "groups": groups, "samples": rows,
            "limitations": ["Sampled results do not establish whole-market or current-listing coverage.",
                            "AI evidence, provider readiness and a generated validated report are distinct capabilities."]}


def markdown_matrix(report):
    """Readable exported matrix; exact records and diagnostics remain in JSON."""
    def cell(value):
        return escape(str(value), quote=False).replace("|", "&#124;").replace("\r", " ").replace("\n", " ")
    lines = [f"Coverage audit as of {cell(report['as_of'])}; mode: {cell(report['data_mode'])}; "
             f"sample: {report['sample_denominator']} listings / {report['unique_issuer_denominator']} verified issuer identities.",
             "", "| Symbol | Exchange | Resolution | Profile | Statements | Eligible models | Contributing models | Quality | Provider restrictions | Unresolved blockers | AI facts |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for row in report["samples"]:
        stages = row["stages"]
        restrictions = "; ".join(item["stage"] + ": " + ", ".join(item["codes"]) for item in row["provider_restrictions"])
        blockers = "; ".join(item["stage"] + ": " + (", ".join(item["codes"]) or item["reason"]) for item in row["unresolved_blockers"])
        eligible = row["eligible_models"]
        fields = [row["requested_symbol"], row["exchange"], stages["symbol_resolution"]["status"], stages["profile"]["status"],
                  stages["statements"]["status"], ", ".join(eligible) if eligible else "None eligible" if eligible == [] else "Not assessed",
                  row["contributing_model_count"] if row["contributing_model_count"] is not None else "Not assessed",
                  row["valuation_quality"] or "Not assessed", restrictions or "None reported",
                  blockers or "None reported", "Yes" if row["ai_evidence_available"] is True else "No" if row["ai_evidence_available"] is False else "Not assessed"]
        lines.append("| " + " | ".join(cell(value) for value in fields) + " |")
    lines.extend(["", "Sampled results do not establish whole-market coverage. Missing values mean unavailable in this audited bundle.",
                  "Exact evidence, periods, model diagnostics and provenance remain in the saved JSON responses."])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("--output")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args()
    result = summarize(json.loads(Path(args.input).read_text(encoding="utf-8")))
    rendered = markdown_matrix(result) if args.format == "markdown" else json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
