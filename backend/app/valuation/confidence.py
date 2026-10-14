"""Explainable quality indicator; never a probability of valuation accuracy."""
from datetime import date
import math

from app.valuation.weighting import GROUPS


def assess_confidence(inputs, models, summary, assumptions):
    active = [model for model in models if model["id"] in summary["effective_weights"]]
    families = {name for name, members in GROUPS.items() if any(model["id"] in members for model in active)}
    factors = []
    factors.append({"name": "Independent model families", "status": "strong" if len(families) >= 3 else "limited",
                    "explanation": f"{len(active)} weighted models represent {len(families)} families. P/E and PEG are related earnings evidence."})
    missing = sorted({field for model in models for field in model["eligibility"].get("missing_inputs", [])})
    factors.append({"name": "Input completeness", "status": "limited" if missing else "strong", "explanation": "Missing inputs: " + ", ".join(missing) if missing else "Applicable models have complete required inputs."})
    metadata = assumptions.get("metadata", {})
    benchmarks = [key for key, item in metadata.items() if item.get("value") is not None and item.get("source_type") in {"benchmark", "policy", "benchmark_assumption"}]
    factors.append({"name": "Assumption quality", "status": "limited" if benchmarks else "review_required",
                    "explanation": "Illustrative benchmark assumptions: " + ", ".join(benchmarks) if benchmarks else "Forecasts and user inputs remain estimates rather than financial facts."})
    observed = (inputs.get("reporting_period") or {}).get("end_date")
    try:
        age = (date.today() - date.fromisoformat(str(observed))).days
    except (TypeError, ValueError):
        age = None
    factors.append({"name": "Statement freshness", "status": "strong" if age is not None and 0 <= age <= 550 else "limited",
                    "explanation": f"Latest annual statement ended {observed}; annual facts are not current market observations."})
    factors.append({"name": "Share denominator", "status": "review_required", "explanation": "Historical diluted weighted shares are dated modeling inputs; they are not a verified current diluted share count."})
    values = [model["fair_value"] for model in active]
    spread = (max(values) - min(values)) / max(1e-12, max(abs(value) for value in values)) if len(values) > 1 else None
    factors.append({"name": "Model agreement", "status": "limited" if spread is None or spread > 0.5 else "moderate",
                    "explanation": "A single model cannot demonstrate agreement." if spread is None else f"Estimate range divided by maximum absolute estimate: {spread:.2f}; correlated agreement is not proof of correctness."})
    concentration = max(summary["effective_weights"].values(), default=0)
    factors.append({"name": "Weight concentration", "status": "limited" if concentration > 0.6 else "moderate", "explanation": f"Largest effective model weight: {concentration:.0%}."})
    terminal = [model["details"].get("terminal_value_contribution", model["details"].get("terminal_contribution")) for model in active]
    terminal = [value for value in terminal if isinstance(value, (int, float)) and math.isfinite(value)]
    factors.append({"name": "Terminal assumptions", "status": "limited" if any(abs(value) > 0.7 for value in terminal) else "review_required", "explanation": "DCF and residual-income estimates can depend heavily on terminal assumptions; review the projection and sensitivity grid."})
    level = "unavailable" if not active else "low" if len(families) < 2 or benchmarks or concentration > 0.6 else "moderate"
    return {"level": level, "indicator": "heuristic_model_quality", "factors": factors,
            "disclaimer": "This describes input and model quality. It is not a statistical probability or a claim of investment accuracy."}
