"""Method and evidence dependence diagnostics; never alter consensus weights."""
from itertools import combinations

from app.valuation.inputs import ALIASES
from app.valuation.models import required_inputs
from app.valuation.weighting import GROUPS
from app.valuation.provenance import USER_TYPES

VERSION = "evidence-dependence-1"


def _record_keys(records):
    keys = set()
    for record in records if isinstance(records, list) else []:
        if not isinstance(record, dict) or not record.get("accn") or not record.get("concept"):
            continue
        keys.add(tuple(str(record.get(field) or "") for field in ("concept", "accn", "unit", "start", "end")))
    return keys


def build_independence(inputs, models, summary, assumptions):
    metadata = assumptions.get("metadata", {})
    fact_names = {target: source for source, target in ALIASES.items()}
    active = [model for model in models if model.get("status") == "valid"
              and summary.get("effective_weights", {}).get(model["id"], 0) > 0]
    dependencies = {}
    for model in active:
        fields = set(model.get("source_quality", {}).get("used_inputs", []))
        if not fields:
            # This is a conservative union when a legacy result has no used
            # path. It cannot prove independent inputs from incomplete metadata.
            fields = {field for path in required_inputs(model["id"]) for field in path}
        observed, estimated, original, seen = set(), set(), set(), set()
        pending = set(fields)
        while pending - seen:
            field = next(iter(pending - seen))
            seen.add(field)
            record = metadata.get(field) or inputs.get("facts", {}).get(fact_names.get(field, field), {})
            fact = inputs.get("facts", {}).get(fact_names.get(field, field), {})
            overridden = (record.get("source_type") in USER_TYPES or record.get("evidence_type") == "user"
                          or record.get("overridden") is True)
            if record.get("value") is not None:
                if overridden or record.get("evidence_type") in {"policy", "estimate", "user"} or record.get("source_type") in {
                    "benchmark_assumption", "historical_estimate", "user_assumption", "user", "policy"}:
                    estimated.add(field)
                else:
                    observed.add(field)
            # An explicit user value replaces the observed input. Historical
            # fact provenance stays in the evidence inventory, not in the
            # active model's shared-source/dependency assessment.
            if not overridden:
                original.update(_record_keys(record.get("provenance") or fact.get("provenance")))
                pending.update(item for item in record.get("dependency_fields", []) if isinstance(item, str))
        dependencies[model["id"]] = (observed, estimated, original)
    pairs = []
    for left, right in combinations(active, 2):
        a, b = dependencies[left["id"]], dependencies[right["id"]]
        pairs.append({"models": [left["id"], right["id"]], "status": "not_established",
            "shared_observed_inputs": sorted(a[0] & b[0]), "shared_assumptions": sorted(a[1] & b[1]),
            "shared_source_records": [dict(zip(("concept", "accn", "unit", "start", "end"), key)) for key in sorted(a[2] & b[2])],
            "reason": "Shared inputs are disclosed. Absence of a detected overlap does not establish independent economic corroboration."})
    families = sorted(group for group, members in GROUPS.items() if any(model["id"] in members for model in active))
    return {"methodology_version": VERSION, "contributing_models": [model["id"] for model in active],
        "contributing_model_count": len(active), "method_families": families, "method_family_count": len(families),
        "pairs": pairs, "corroboration": {"status": "unavailable" if len(active) < 2 else "unverified",
            "reason": "Fewer than two models contribute; independent corroboration is unavailable." if len(active) < 2 else
                "Method-family diversity and an absence of detected shared inputs do not prove independent corroboration; source and economic review remain required."}}
