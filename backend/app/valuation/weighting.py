"""Group-aware recommendations and aggregation of signed equity estimates."""
import math

from app.valuation.schemas import MODEL_IDS

GROUPS = {
    "cash_flow": {"fcff": 3, "fcfe": 2},
    "earnings": {"pe": 4, "peg": 1},
    "enterprise_multiples": {"evEbitda": 3, "evRevenue": 1},
    "book_equity": {"residual": 4, "pb": 2, "graham": 1},
    "distributions": {"dividend": 2, "affo": 4},
}
GROUP_BUDGETS = {"cash_flow": 35, "earnings": 25, "enterprise_multiples": 20, "book_equity": 15, "distributions": 20}
AGGREGATION_VERSION = "family-weighted-mean-1"
FAMILY_LABELS = {"cash_flow": "Discounted cash flow", "earnings": "Earnings multiples",
                 "enterprise_multiples": "Enterprise multiples", "book_equity": "Book equity",
                 "distributions": "Distributions"}


def aggregation_diagnostics(models, summary, user_weights=()):
    """Describe the existing arithmetic; ranges are not confidence intervals."""
    active = [model for model in models if model["id"] in summary["effective_weights"]]
    values = [model["fair_value"] for model in active]
    sources = {model["id"]: "user" if model["id"] in user_weights else "default" for model in active}
    origin = "mixed" if len(set(sources.values())) > 1 else next(iter(sources.values()), "default")
    spread = ((max(values) - min(values)) / max(1e-12, max(abs(value) for value in values))
              if len(values) > 1 else None)
    fields = {}
    for model in active:
        for key in model.get("source_quality", {}).get("used_inputs", []):
            fields.setdefault(key, []).append(model["id"])
    warnings = ["Method families describe related financial frameworks; distinct families do not establish independent evidence."]
    if len(values) < 2:
        warnings.append("A single contributing model cannot establish model agreement or a defensible model range.")
    elif spread > 0.5:
        warnings.append("Contributing estimates materially disagree: their range exceeds half the largest absolute estimate; no outlier is silently removed.")
    if any(value <= 0 for value in values):
        warnings.append("Nonpositive equity estimates are preserved; a range crossing zero requires economic interpretation.")
    if fields and any(len(ids) > 1 for ids in fields.values()):
        warnings.append("Contributing models share inputs or assumptions; agreement is not independent confirmation.")
    return {"methodology_version": AGGREGATION_VERSION, "method": "normalized_weighted_mean",
            "weight_source": origin, "per_model_weight_sources": sources,
            "estimate_range": {"minimum": min(values), "maximum": max(values)} if len(values) > 1 else None,
            "dispersion": {"status": "material_disagreement" if spread > 0.5 else "limited_agreement",
                           "relative_spread": spread} if spread is not None else None,
            "shared_assumptions": [{"key": key, "model_ids": ids} for key, ids in sorted(fields.items()) if len(ids) > 1],
            "family_weights": {family: math.fsum(summary["effective_weights"].get(model["id"], 0) for model in active if model["id"] in members)
                               for family, members in GROUPS.items() if any(model["id"] in members for model in active)},
            "warnings": warnings}


def comparisons(fair_value, price):
    if fair_value is None or not math.isfinite(fair_value) or price is None or not math.isfinite(price) or price <= 0:
        return {"upside": None, "margin_of_safety": None}
    upside = (fair_value / price - 1) * 100
    margin = (fair_value - price) / fair_value * 100 if fair_value > 0 else None
    return {"upside": upside if math.isfinite(upside) else None,
            "margin_of_safety": margin if margin is not None and math.isfinite(margin) else None}


def suggest_weights(models):
    """Family budgets prevent adding PEG from doubling earnings evidence."""
    weights, reasons = {}, {}
    for group, members in GROUPS.items():
        present = [model for model in models if model["id"] in members and model["status"] == "valid"]
        total = sum(members[model["id"]] for model in present)
        for model in present:
            quality = 0.7 if model["eligibility"]["status"] == "available_with_warnings" else 1
            source = model.get("source_quality", {})
            source_factor = {"low": 0.6, "moderate": 0.85, "supported": 1}.get(source.get("level"), 1) if source.get("automatic_evidence") else 1
            quality *= source_factor
            weights[model["id"]] = GROUP_BUDGETS[group] * members[model["id"]] / total * quality
            reasons[model["id"]] = f"Shares the {group.replace('_', ' ')} family budget; related methods do not count as independent confirmation."
            if source_factor < 1:
                reasons[model["id"]] += f" Automatic source quality ({source['level']}) applies a disclosed {source_factor:.0%} preference factor; this is a weighting policy, not a probability of accuracy."
    return weights, reasons


def combine_valuations(models, enabled, weights, price=None):
    selected = [model for model in models if model["id"] in enabled and model["id"] in MODEL_IDS and not model.get("diagnostic")]
    if any(isinstance(weights.get(model["id"], 0), bool) or not isinstance(weights.get(model["id"], 0), (int, float)) or not math.isfinite(weights.get(model["id"], 0)) or weights.get(model["id"], 0) < 0 for model in selected):
        return {"fair_value": None, **comparisons(None, price), "effective_weights": {}, "count": 0,
                "warnings": ["Configured weights must be finite nonnegative numbers."]}
    included = [model for model in selected if model["status"] == "valid" and model.get("fair_value") is not None and math.isfinite(model["fair_value"]) and weights.get(model["id"], 0) > 0]
    total = sum(weights[model["id"]] for model in included)
    warnings = [f"{model['name']} is excluded until its required inputs and assumptions are valid; its configured weight is retained." for model in selected if model not in included and weights.get(model["id"], 0) > 0]
    if total <= 0 or not math.isfinite(total):
        return {"fair_value": None, **comparisons(None, price), "effective_weights": {}, "count": 0,
                "warnings": warnings + ["No enabled valid models have a positive weight."]}
    effective = {model["id"]: weights[model["id"]] / total for model in included}
    value = math.fsum(model["fair_value"] * effective[model["id"]] for model in included)
    if len(included) == 1:
        warnings.append("This is a single-model estimate; no independent model confirmation is available.")
    if any(model["fair_value"] <= 0 for model in included):
        warnings.append("Signed nonpositive equity estimates are retained, not clipped to zero; margin of safety requires positive weighted fair value.")
    if not math.isfinite(value):
        return {"fair_value": None, **comparisons(None, price), "effective_weights": {}, "count": 0,
                "warnings": warnings + ["The aggregate estimate is nonfinite and unavailable."]}
    return {"fair_value": value, **comparisons(value, price), "effective_weights": effective, "count": len(included), "warnings": warnings}
