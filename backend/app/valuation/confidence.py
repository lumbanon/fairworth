"""Versioned, conservative diagnostics; never a probability of valuation accuracy."""
from datetime import date

from app.valuation.inputs import day, number
from app.valuation.provenance import FINANCIAL_FIELDS
from app.valuation.weighting import FAMILY_LABELS, GROUPS, aggregation_diagnostics

QUALITY_VERSION = "valuation-quality-2"


def snapshot_date(inputs):
    """Assess archived evidence at its frozen snapshot, not at every replay date."""
    candidates = [inputs.get("automatic_evidence", {}).get("as_of_date"),
                  inputs.get("financial_retrieved_at"), (inputs.get("market") or {}).get("retrieved_at")]
    for raw in candidates:
        observed = day(str(raw or "")[:10])
        if observed is not None:
            return observed
    return date.today()


def _active(models, summary):
    return [model for model in models if model["id"] in summary["effective_weights"]]


def assess_confidence(inputs, models, summary, assumptions):
    active = _active(models, summary)
    families = [family for family, members in GROUPS.items() if any(model["id"] in members for model in active)]
    used = {field for model in active for field in model.get("source_quality", {}).get("used_inputs", [])}
    metadata = assumptions.get("metadata", {})
    policies = sorted(field for field in used if metadata.get(field, {}).get("value") is not None
                      and (metadata[field].get("evidence_type") == "policy" or metadata[field].get("policy_dependencies")
                           or metadata[field].get("source_type") in {"benchmark", "policy", "benchmark_assumption", "policy_estimate"}))
    user = sorted(field for field in used if metadata.get(field, {}).get("overridden")
                  or metadata.get(field, {}).get("evidence_type") == "user")
    as_of = snapshot_date(inputs)
    observed = day((inputs.get("reporting_period") or {}).get("end_date"))
    age = (as_of - observed).days if observed else None
    fresh = age is not None and 0 <= age <= 550
    relevant = used | {field for key in used for field in FINANCIAL_FIELDS.get(key, [])}
    relevant |= {"currency", "reporting_currency", "financial_period", "share_basis"}
    source_warnings = list(inputs.get("warnings", []))
    source_warnings.extend(warning for field in relevant for warning in inputs.get("facts", {}).get(field, {}).get("warnings", []))
    source_warnings.extend(warning for field in used for warning in metadata.get(field, {}).get("warnings", []))
    stale_cache = inputs.get("data_status") in {"stale", "expired"} or any(
        isinstance(warning, dict) and warning.get("code") in {"stale_provider_failure", "stale_cache", "expired_financial_cache", "stale_financial_snapshot"}
        for warning in inputs.get("warnings", []))
    conflicts = sorted({warning.get("code") for warning in source_warnings
                        if isinstance(warning, dict) and warning.get("field") in relevant and warning.get("code") and
                        any(term in warning["code"] for term in ("incompatible", "ambiguous", "conflicting"))})
    factors = [{"name": "Methodological coverage", "status": "moderate" if len(families) >= 2 else "limited",
                "explanation": f"{len(active)} contributing models represent {len(families)} method families. Families do not prove independent evidence."},
               {"name": "Contributing assumptions", "status": "limited" if policies else "review_required",
                "explanation": ("Contributing research policies: " + ", ".join(policies) + "." if policies else
                                "No identified policy default contributes to these models; all forecasts remain estimates.")
                               + (" Explicit user inputs: " + ", ".join(user) + "." if user else "")},
               {"name": "Statement freshness", "status": "moderate" if fresh else "limited",
                "explanation": f"Financial period {observed or 'unavailable'}; annual facts are dated inputs, not current observations. Freshness uses the retained assessment snapshot."},
               {"name": "Financial cache freshness", "status": "limited" if stale_cache else "review_required",
                "explanation": "The provider failed or the financial cache expired; retained data is explicitly stale despite its original snapshot date." if stale_cache else "No explicit stale financial-cache status was reported; retained statement dates remain available for review."},
               {"name": "Period and source compatibility", "status": "limited" if conflicts else "review_required",
                "explanation": "Compatibility issues: " + ", ".join(conflicts) if conflicts else "No selected-input compatibility conflict was reported; source definitions and modeling assumptions still require review."}]
    share_basis = inputs.get("basis", {})
    factors.append({"name": "Share denominator", "status": "review_required",
                    "explanation": (f"Dated common shares observed {share_basis.get('valuation_share_observation_date')}; annual diluted EPS retains its own reported denominator."
                                    if share_basis.get("valuation_share_denominator") else
                                    "Historical diluted weighted shares or explicit user estimates are dated model inputs, not verified current diluted shares.")})
    values = [model["fair_value"] for model in active]
    spread = (max(values) - min(values)) / max(1e-12, max(abs(value) for value in values)) if len(values) > 1 else None
    disagreement = spread is not None and spread > 0.5
    factors.append({"name": "Model agreement", "status": "limited" if spread is None or disagreement else "moderate",
                    "explanation": "A single model cannot demonstrate agreement." if spread is None else
                                   f"Range / largest absolute contributing estimate: {spread:.2f}. Related assumptions can produce correlated agreement."})
    concentration = max(summary["effective_weights"].values(), default=0)
    factors.append({"name": "Weight concentration", "status": "limited" if concentration > 0.6 else "moderate",
                    "explanation": f"Largest effective model weight: {concentration:.0%}; unavailable models never contribute zero-valued estimates."})
    terminal_risks, spread_risks = [], []
    for model in active:
        detail = model.get("details", {})
        terminal = number(detail.get("terminal_value_contribution", detail.get("terminal_contribution")))
        if terminal is None and number(detail.get("terminal_present_value")) is not None and number(detail.get("equity_value")) not in (None, 0):
            terminal = detail["terminal_present_value"] / detail["equity_value"]
        if model["id"] == "dividend":
            terminal_pv = number(detail.get("terminal_present_value"))
            terminal = terminal_pv / model["fair_value"] if terminal_pv is not None and model["fair_value"] else 1
        if terminal is not None and abs(terminal) > 0.8:
            terminal_risks.append(model["id"])
        rate = number(detail.get("discount_rate", detail.get("cost_of_equity")))
        terminal_growth = number(detail.get("terminal_growth", detail.get("dividend_growth")))
        if rate is not None and terminal_growth is not None and rate - terminal_growth <= 0.01:
            spread_risks.append(model["id"])
    factors.append({"name": "Terminal and discount sensitivity", "status": "limited" if terminal_risks or spread_risks else "review_required",
                    "explanation": ("Terminal contribution above 80%: " + ", ".join(terminal_risks) + ". " if terminal_risks else "")
                                   + ("Discount/terminal-growth spread at most one percentage point: " + ", ".join(spread_risks) + ". " if spread_risks else "")
                                   + "These disclosed quality thresholds flag sensitivity; equations and signed cash flows are preserved."})
    low_sources = any(model.get("source_quality", {}).get("level") == "low" for model in active)
    low = (len(families) < 2 or bool(policies) or any(model.get("classification") == "policy_based" for model in active)
           or concentration > 0.6 or not fresh or stale_cache or bool(conflicts) or disagreement or bool(terminal_risks)
           or bool(spread_risks) or low_sources or any(value <= 0 for value in values))
    level = "unavailable" if not active else "low" if low else "moderate"
    return {"level": level, "indicator": "heuristic_model_quality", "methodology_version": QUALITY_VERSION,
            "assessed_as_of": as_of.isoformat(), "factors": factors,
            "contributing_policy_inputs": policies, "contributing_user_inputs": user,
            "disclaimer": "This describes input and model quality. It is not a statistical probability or a claim of investment accuracy."}


def valuation_diagnostics(inputs, models, summary, assumptions, confidence, user_weights=()):
    active = _active(models, summary)
    factors = [factor for factor in confidence["factors"] if factor["name"] in {"Statement freshness", "Financial cache freshness", "Period and source compatibility", "Share denominator"}]
    has_facts = any(number(fact.get("value")) is not None for fact in inputs.get("facts", {}).values())
    quality = "unavailable" if not has_facts else "limited" if any(factor["status"] == "limited" for factor in factors) else "review_required"
    families = [{"id": family, "label": FAMILY_LABELS[family], "model_ids": [model["id"] for model in active if model["id"] in members]}
                for family, members in GROUPS.items() if any(model["id"] in members for model in active)]
    return {"methodology_version": QUALITY_VERSION,
            "data_quality": {"level": quality, "factors": factors,
                             "reasons": [factor["explanation"] for factor in factors],
                             "disclaimer": "Underlying data quality, model coverage and valuation confidence describe different limitations."},
            "coverage": {"eligible_count": sum(model["status"] == "valid" for model in models),
                         "applicable_count": sum(model["eligibility"]["status"] != "ineligible" for model in models),
                         "contributing_count": len(active), "contributing_models": [model["id"] for model in active],
                         "method_family_count": len(families), "families": families,
                         "excluded_models": [{"model_id": model["id"], "status": "disabled_or_zero_weight" if model["status"] == "valid" else model["eligibility"]["status"],
                                               "reason": "This valid model is disabled or has no positive configured weight." if model["status"] == "valid" else model["eligibility"]["reason"],
                                               "missing_inputs": model["eligibility"].get("missing_inputs", []),
                                               "input_paths": model["eligibility"].get("input_paths", [])}
                                              for model in models if model not in active]},
            "aggregation": aggregation_diagnostics(models, summary, user_weights)}
