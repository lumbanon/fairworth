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
            weights[model["id"]] = GROUP_BUDGETS[group] * members[model["id"]] / total * quality
            reasons[model["id"]] = f"Shares the {group.replace('_', ' ')} family budget; related methods do not count as independent confirmation."
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
