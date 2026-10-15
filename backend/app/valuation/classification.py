"""Classify only evidence that materially contributes to an intrinsic estimate."""
from collections import defaultdict

from app.valuation.models import required_inputs
from app.valuation.provenance import POLICY_TYPES, USER_TYPES

LABELS = {"evidence_supported": "Evidence-supported estimate", "policy_based": "Policy-based illustrative estimate",
          "user_defined": "User-defined estimate", "unavailable": "Unavailable"}
DEPENDENCIES = {
    "forward_eps": ["trailing_eps", "earnings_growth"],
    "forecast_revenue": ["revenue", "revenue_growth"],
    "forecast_ebitda": ["forecast_revenue", "ebitda_margin"],
    "projected_revenue": ["revenue", "revenue_growth", "terminal_growth", "forecast_years"],
    "wacc": ["cost_of_equity", "cost_of_debt", "tax_rate"],
    "cost_of_equity": ["risk_free_rate", "beta", "equity_risk_premium"],
}


def classify_model(model, assumptions, effective_values):
    if model["status"] != "valid":
        return {"classification": "unavailable", "classification_reasons": list(model.get("warnings", [])),
                "source_quality": {"level": "unavailable", "warnings": list(model.get("warnings", [])), "categories": []}}
    alternatives = required_inputs(model["id"])
    complete = [path for path in alternatives if all(effective_values.get(key) is not None for key in path)]
    selected = complete[0] if complete else []
    if model["id"] in {"fcff", "fcfe"} and any("revenue" in row for row in model.get("details", {}).get("projection", [])):
        selected = next((path for path in complete if "projected_revenue" in path), None) or next((path for path in complete if "revenue_growth" in path and "nwc_ratio" in path), selected)
    fields = set(selected)
    for confirmation in ("share_basis_confirmed", "common_equity_basis_confirmed", "book_value_meaningful", "clean_surplus_confirmed", "stable_dividend_confirmed", "affo_basis_confirmed"):
        if effective_values.get(confirmation) is True:
            if confirmation == "share_basis_confirmed" or confirmation == "common_equity_basis_confirmed" and model["id"] in {"pb", "residual", "graham"} or confirmation == "book_value_meaningful" and model["id"] in {"pb", "residual", "graham"} or confirmation == "clean_surplus_confirmed" and model["id"] == "residual" or confirmation == "stable_dividend_confirmed" and model["id"] == "dividend" or confirmation == "affo_basis_confirmed" and model["id"] == "affo":
                fields.add(confirmation)
    metadata = assumptions.get("metadata", {})
    examined, kinds, warnings, reasons, automatic_quality = set(), set(), [], [], []
    while fields - examined:
        field = next(iter(fields - examined))
        examined.add(field)
        record = metadata.get(field, {})
        if record.get("source_category") in {"historical_company_valuation", "derived_historical_estimate"}:
            quality = record.get("quality")
            level = quality.get("level") if isinstance(quality, dict) else quality
            if level in {"low", "moderate", "supported"}:
                automatic_quality.append(level)
        kind = record.get("evidence_type")
        source_type = record.get("source_type")
        if record.get("overridden") or kind == "user" or source_type in USER_TYPES:
            kinds.add("user")
            reasons.append(f"{field} is an explicit user assumption.")
            # An explicit forecast replaces its derived inputs; they no longer
            # contribute to this value or its classification.
            continue
        if kind == "policy" or source_type in POLICY_TYPES or record.get("policy_dependencies"):
            kinds.add("policy")
            reasons.append(f"{field} depends on disclosed modeling policy.")
        if kind in {"fact", "estimate"}:
            kinds.add(kind)
        warnings.extend(str(item.get("message", "")) if isinstance(item, dict) else str(item) for item in record.get("warnings", []))
        dependencies = record.get("dependency_fields")
        if dependencies is None and record.get("computed_only"):
            dependencies = DEPENDENCIES.get(field, [])
        fields.update(dependencies or [])
    category = "user_defined" if "user" in kinds else "policy_based" if "policy" in kinds else "evidence_supported"
    if not reasons:
        reasons = ["Inputs pass financial compatibility checks and use documented observed or derived evidence; this is an estimate, not a verified fair price."]
    return {"classification": category, "classification_reasons": list(dict.fromkeys(reasons)),
            "source_quality": {"level": "low" if "low" in automatic_quality else "moderate" if "moderate" in automatic_quality else "review_required" if warnings or category != "evidence_supported" else "supported",
                               "automatic_evidence": bool(automatic_quality),
                               "warnings": list(dict.fromkeys(warnings)), "categories": sorted(kinds), "used_inputs": sorted(examined)}}


def classify_summary(summary, models):
    groups = defaultdict(lambda: {"weight": 0.0, "model_ids": []})
    warnings = []
    for model in models:
        weight = summary["effective_weights"].get(model["id"], 0)
        if weight <= 0:
            continue
        category = model.get("classification", "unavailable")
        groups[category]["weight"] += weight
        groups[category]["model_ids"].append(model["id"])
        warnings.extend(model.get("source_quality", {}).get("warnings", []))
    category = "unavailable" if not groups else "user_defined" if "user_defined" in groups else "policy_based" if "policy_based" in groups else "evidence_supported"
    if summary["count"] == 1:
        warnings.append("Single-model estimate: there is no independent model confirmation.")
    return {"classification": category,
            "composition": [{"classification": kind, **detail} for kind, detail in sorted(groups.items())],
            "source_warnings": list(dict.fromkeys(warnings))}
