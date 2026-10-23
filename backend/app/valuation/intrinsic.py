"""Present existing intrinsic outputs separately from current quote comparisons.

No number here is an input to a valuation formula, eligibility, or publication.
"""
from copy import deepcopy
from datetime import date, timedelta
import math

from app.valuation.coverage import MODEL_ASSUMPTIONS

VERSION = "intrinsic-presentation-1"


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _horizon(period, model_ids, assumptions):
    try:
        end = date.fromisoformat(period["end_date"])
        first_start = end + timedelta(days=1)
        # Calendar endpoints are declared scenario conventions. They are not a
        # claim that a new fiscal statement or forecast was reported by SEC.
        first_end = end.replace(year=end.year + 1)
    except (KeyError, TypeError, ValueError):
        first_start = first_end = None
    perpetuity = "dividend" in model_ids
    forecast = assumptions.get("forecast_years", {}).get("value")
    return {"basis": "scenario_calendar_assumption", "first_forecast_year": 1,
            "first_forecast_start": first_start.isoformat() if first_start else None,
            "first_forecast_end": first_end.isoformat() if first_end else None,
            "explicit_years": None if perpetuity else forecast,
            "terminal": "constant_growth_perpetuity" if perpetuity else "model_specific",
            "label": "First annual scenario period after the reported fiscal year, followed by constant-growth dividends in perpetuity."
                     if perpetuity else "Forecast periods follow the dated reported financial baseline; forecasts are estimates.",
            "reported_forecast": False}


def intrinsic_presentation(inputs, case, market, checks, clock):
    summary = case.get("summary") or {}
    value = summary.get("fair_value")
    available = _finite(value)
    contributing = set(summary.get("effective_weights") or {})
    model_ids = [model["id"] for model in case.get("models", []) if model["id"] in contributing]
    metadata = case.get("assumptions", {}).get("metadata", {})
    fields = set().union(*(MODEL_ASSUMPTIONS.get(model_id, set()) for model_id in model_ids))
    if "dividend" in model_ids:
        fields |= {"dividend_per_share", "stable_dividend_confirmed"}
    assumptions = {field: deepcopy(metadata[field]) for field in sorted(fields)
                   if field in metadata and metadata[field].get("value") is not None}
    period = deepcopy(inputs.get("reporting_period") or {})
    # Reported per-share declarations retain their exact source records. Never
    # substitute issuer dividends / weighted-average diluted shares.
    fact_names = {"declared_common_dividend_per_share"} if model_ids == ["dividend"] else set(inputs.get("facts") or {})
    source_facts = {field: deepcopy(record) for field, record in inputs.get("facts", {}).items()
                    if field in fact_names and isinstance(record, dict) and record.get("value") is not None}
    source_ids = sorted({record["accn"] for fact in source_facts.values()
                         for record in fact.get("provenance", []) if isinstance(record, dict) and record.get("accn")})
    limitations = ["A deterministic intrinsic estimate and a current market comparison have separate evidence requirements.",
                  "Dated source financials and explicit scenario assumptions do not establish current published fair value.",
                  "One model provides no independent model confirmation."] if len(model_ids) == 1 else [
                      "Dated source financials and explicit scenario assumptions do not establish current published fair value."]
    if "dividend" in model_ids:
        limitations += ["The dividend baseline is the reported common dividend declared per share, not measured cash paid.",
                        "Constant payout sustainability, future payment, growth and required return are scenario assumptions.",
                        "This cash-dividend-only scenario excludes repurchases and changes in payout policy; it is not a comprehensive enterprise valuation."]
    intrinsic = {"methodology_version": VERSION, "status": "available" if available else "unavailable",
                 "value": value if available else None, "currency": inputs.get("currency"),
                 "model_ids": model_ids, "classification": summary.get("classification", "unavailable"),
                 "workflow": "user_assisted" if summary.get("classification") == "user_defined" else "automatic_default",
                 "financial_observation_date": period.get("end_date"), "financial_period": period,
                 "valuation_anchor_date": period.get("end_date"),
                 "calculated_at": clock.isoformat(), "source_retrieved_at": inputs.get("financial_retrieved_at"),
                 "forecast_horizon": _horizon(period, model_ids, assumptions), "assumptions": assumptions,
                 "source_identifiers": source_ids, "source_facts": source_facts,
                 "financial_import": deepcopy(inputs.get("financial_import")),
                 "current_eligible": case.get("publication", {}).get("current_eligible") is True,
                 "publication_type": case.get("publication", {}).get("result_type", "unavailable"),
                 "limitations": limitations}
    if inputs.get("dated_intrinsic_scope"):
        context = deepcopy(inputs["dated_intrinsic_scope"])
        context.pop("historical_identity", None)
        intrinsic["evidence_context"] = context
        intrinsic["limitations"] += context.get("limitations", [])
        intrinsic["limitations"].append("The dividend-discount value is anchored at the financial baseline date. The later evidence and calculation clocks do not roll it forward or imply a present-day target.")
    current = checks.get("market_price", {}).get("status") == "available"
    manual = market.get("source_type") == "user"
    comparable = available and _finite(market.get("price")) and market["price"] > 0
    status = "user_scenario" if comparable and manual else "available" if comparable and current else "stale" if comparable else "unavailable"
    comparison = {"status": status, "current": status == "available", "price": market.get("price"),
                  "currency": market.get("currency"), "provider": market.get("provider"),
                  "observed_at": market.get("price_timestamp"), "retrieved_at": market.get("retrieved_at"),
                  "source_type": market.get("source_type"),
                  "upside": summary.get("upside") if status in {"available", "user_scenario"} else None,
                  "margin_of_safety": summary.get("margin_of_safety") if status in {"available", "user_scenario"} else None,
                  "reason": "Explicit user comparison price; not a provider observation or current market verification." if manual else checks.get("market_price", {}).get("reason")}
    return intrinsic, comparison
