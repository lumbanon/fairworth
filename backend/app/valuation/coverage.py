"""Explain existing engine decisions without supplying inputs or changing values.

Coverage is an evidence inventory, never an additional eligibility engine. Quotes,
listing freshness and historical depth are independent from intrinsic estimates.
"""
from collections import Counter
from copy import deepcopy
from datetime import UTC, datetime
import math

from app.services.security_identity import applicability, security_identity
from app.valuation.engine import calculate_valuation, calculation_values
from app.valuation.inputs import ALIASES
from app.valuation.history import analyze_history
from app.valuation.models import required_inputs
from app.valuation.schemas import MODEL_IDS
from app.valuation.weighting import GROUPS
from app.valuation.publication import publication_status
from app.valuation.independence import build_independence

VERSION = "model-coverage-2"
MODEL_ASSUMPTIONS = {
    "fcff": {"wacc", "terminal_growth", "forecast_years", "projected_fcff", "fcff", "cash_flow_growth", "revenue_growth", "capex_ratio", "da_ratio", "nwc_ratio", "operating_margin", "tax_rate", "projected_revenue"},
    "fcfe": {"cost_of_equity", "terminal_growth", "forecast_years", "projected_fcfe", "fcfe", "cash_flow_growth", "revenue_growth", "capex_ratio", "da_ratio", "nwc_ratio", "net_margin", "net_borrowing", "projected_revenue"},
    "pe": {"forward_eps", "earnings_growth", "target_pe"},
    "evEbitda": {"forecast_ebitda", "forecast_revenue", "ebitda_margin", "target_ev_ebitda", "revenue_growth"},
    "evRevenue": {"forecast_revenue", "target_ev_revenue", "revenue_growth"},
    "peg": {"forward_eps", "earnings_growth", "target_peg"}, "graham": set(),
    "dividend": {"dividend_growth", "cost_of_equity", "projected_dividends", "terminal_growth", "forecast_years"},
    "residual": {"return_on_equity", "payout_ratio", "cost_of_equity", "terminal_growth", "forecast_years"},
    "pb": {"target_pb"}, "affo": {"forecast_affo", "target_p_affo"},
}
PERIOD_METRICS = ("revenue", "net_income", "operating_income", "operating_cash_flow",
    "capital_expenditures", "free_cash_flow", "cash_and_cash_equivalents", "total_debt",
    "interest_expense", "total_assets", "total_liabilities", "shareholders_equity",
    "weighted_average_diluted_shares", "weighted_average_basic_shares", "shares_outstanding",
    "diluted_eps", "dividends_paid", "depreciation_and_amortization")
REASON_CODES = {
    "share_class_basis_unverified": "share_basis_unverified",
    "foreign_share_basis_unverified": "share_basis_unverified",
    "adr_ratio_unverified": "adr_ratio_unverified",
    "adr_metadata_unverified": "adr_ratio_unverified",
    "foreign_currency_basis_unverified": "currency_mismatch",
    "unverified_reporting_currency": "currency_mismatch",
    "incompatible_reporting_currency": "currency_mismatch",
    "financial_institution_enterprise_framework": "sector_model_incompatible",
    "reit_gaap_earnings_not_cash_earnings": "sector_model_incompatible",
    "not_a_reit": "sector_model_incompatible",
    "unsupported_instrument_type": "sector_model_incompatible",
    "income_earnings_basis_mismatch": "share_basis_unverified",
    "preferred_and_common_book_scope_unverified": "common_equity_scope_unverified",
    "noncontrolling_equity_scope": "common_equity_scope_unverified",
}
MESSAGES = {
    "financial_statements_missing": "No compatible normalized annual statements are available.",
    "required_metric_missing": "A required financial input or explicit assumption is unavailable.",
    "share_basis_unverified": "Issuer amounts and the selected security's per-share economics have not been reconciled.",
    "currency_mismatch": "Compatible reporting and trading currencies have not been established.",
    "discount_rate_unavailable": "A defensible required discount rate is unavailable; no rate is invented.",
    "historical_multiple_unavailable": "No supported target multiple is available from permitted history or an explicit assumption.",
    "sector_model_incompatible": "The issuer or security does not support this valuation framework.",
    "insufficient_cash_flow_history": "Complete operating working-capital or financing evidence is unavailable for this cash-flow path.",
    "unsupported_accounting_regime": "Compatible normalized accounting evidence is unavailable; no accounting or FX conversion is inferred.",
    "period_mismatch": "Required input observations have incompatible reporting periods or filing contexts.",
}


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _timestamp(value):
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else None
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result.astimezone(UTC) if result.tzinfo else None
    except (TypeError, ValueError):
        return None


def reporting_periods(inputs):
    rows = []
    for period in inputs.get("annual_periods", []):
        facts = period.get("facts", {})
        metrics = period.get("metrics", {})
        # Canonical facts, including quarantined values, are authoritative over
        # an otherwise present raw metric. Zero is an observation, not missing.
        usable = lambda key: _finite(facts[key].get("value")) if key in facts else _finite(metrics.get(key))
        available = [key for key in PERIOD_METRICS if usable(key)]
        identifiers = sorted({str(part["accn"]) for fact in facts.values()
                              for part in fact.get("provenance", []) if isinstance(part, dict) and part.get("accn")})
        rows.append({**{key: period.get(key) for key in ("fiscal_year", "fiscal_period", "start_date", "end_date")},
            "available_metrics": available, "missing_metrics": [key for key in PERIOD_METRICS if key not in available],
            "source_identifiers": identifiers,
            "warnings": list(dict.fromkeys(str(item.get("message", "")) for item in period.get("warnings", []) if isinstance(item, dict)))})
    return sorted(rows, key=lambda row: str(row.get("end_date") or ""), reverse=True)


def compatibility(inputs, market, as_of):
    basis, company = inputs.get("basis", {}), inputs.get("company", {})
    shares = basis.get("share_basis_verified") is True
    currency = inputs.get("currency")
    provider_market = inputs.get("market") or market
    observed_currency = provider_market.get("provider_currency", provider_market.get("currency"))
    comparable = bool(currency and observed_currency and currency == observed_currency)
    quote_date = _timestamp(provider_market.get("price_timestamp"))
    price = provider_market.get("price")
    valid_quote = (_finite(price) and price > 0 and comparable and quote_date is not None
                   and provider_market.get("source_type") != "user")
    fresh_quote = bool(valid_quote and 0 <= (as_of - quote_date).total_seconds() <= 172800
                       and provider_market.get("status") == "fresh" and provider_market.get("source_type") != "user")
    quote_status = "available" if fresh_quote else "stale" if valid_quote and quote_date <= as_of else "unavailable"
    unsupported = any(item.get("code") == "unsupported_ifrs_normalization" for item in inputs.get("warnings", []))
    valid_facts = any(_finite(fact.get("value")) for period in inputs.get("annual_periods", []) for fact in period.get("facts", {}).values())
    return {
        "share_basis": {"status": "available" if shares else "unverified",
            "reason": "Selected-security share basis is supported; the modeled annual denominator remains dated." if shares else MESSAGES["share_basis_unverified"]},
        "currency": {"status": "available" if comparable else "incompatible" if currency and observed_currency else "unverified",
            "reason": "Reporting and observed quote currencies match; no FX conversion is used." if comparable else MESSAGES["currency_mismatch"]},
        "reporting_regime": {"status": "incompatible" if unsupported else "available" if valid_facts else "unverified",
            "reason": MESSAGES["unsupported_accounting_regime"] if unsupported else "Validated facts in compatible normalized annual evidence are retained; completeness is assessed separately." if valid_facts else "No compatible normalized annual evidence establishes the reporting basis."},
        "market_price": {"status": quote_status, "observation_date": quote_date.isoformat() if quote_date else None,
            "reason": "A dated compatible provider quote is within the two-day freshness policy." if fresh_quote else "The provider quote is dated and stale; it does not establish a current market price." if quote_status == "stale" else "A valid, dated, compatible provider quote is unavailable. Manual comparison prices are not fresh provider observations."},
    }


def model_blockers(inputs, model):
    decision = model.get("eligibility", {})
    if model.get("status") == "valid" and decision.get("status") not in {"ineligible", "unavailable"}:
        return []
    groups = {}
    def add(code, fields=(), message=None):
        item = groups.setdefault(code, {"code": code, "message": message or MESSAGES.get(code) or decision.get("reason") or "The engine rejects this model.", "fields": []})
        item["fields"] = sorted(set(item["fields"]) | set(fields))
    if not inputs.get("annual_periods"):
        add("financial_statements_missing")
    company = inputs.get("company", {})
    if company.get("instrument_id") and company.get("identity_status") != "verified":
        add("security_identity_unverified", message="The selected instrument, listing and issuer linkage is not currently verified; original source proof dates are retained independently of financial retrieval.")
    for code in decision.get("reason_codes", []):
        if code not in {"missing_inputs", "inputs_complete"}:
            add(REASON_CODES.get(code, code))
    for key in decision.get("missing_inputs", []):
        code = ("discount_rate_unavailable" if key in {"wacc", "cost_of_equity"}
                else "historical_multiple_unavailable" if key.startswith("target_")
                else "share_basis_unverified" if key in {"share_basis_confirmed", "common_equity_earnings_basis"}
                else "currency_mismatch" if "currency" in key else "required_metric_missing")
        add(code, [key])
        source_name = next((source for source, target in ALIASES.items() if target == key), key)
        fact = inputs.get("facts", {}).get(source_name, {})
        if any(item.get("code") in {"incompatible_fact_period", "incompatible_annual_period", "incompatible_fact_context", "incompatible_filing_context"}
               for item in fact.get("warnings", []) if isinstance(item, dict)):
            add("period_mismatch", [key])
    if model["id"] in {"fcff", "fcfe"}:
        # Explain all component alternatives instead of only the engine's
        # shortest route. A complete direct path still has no blockers above.
        fields = [key for key in decision.get("missing_inputs", []) if key in {"change_nwc", "nwc_ratio", "net_borrowing"}]
        if fields:
            add("insufficient_cash_flow_history", fields)
    if any(item.get("code") == "unsupported_ifrs_normalization" for item in inputs.get("warnings", [])):
        add("unsupported_accounting_regime")
    if not groups:
        add("invalid_model_assumptions", message="; ".join(model.get("warnings", [])) or decision.get("reason"))
    return list(groups.values())


def _candidate_sources(inputs, assumptions, model_id):
    """Each alternative retains original facts and effective edits separately."""
    metadata = assumptions.get("metadata", {})
    values = calculation_values(inputs, assumptions)
    original_names = {target: source for source, target in ALIASES.items()}
    records = {}
    for key in sorted({field for path in required_inputs(model_id) for field in path}):
        fact = inputs.get("facts", {}).get(original_names.get(key, key), {})
        record = metadata.get(key) or fact
        records[key] = {"value": deepcopy(values.get(key)),
            "source_type": record.get("source_type", "unavailable"),
            "evidence_type": record.get("evidence_type"), "unit": record.get("unit"),
            "source_identifiers": deepcopy(record.get("source_identifiers", [])),
            "observation_date": record.get("observation_date"),
            "financial_period": deepcopy(record.get("financial_period", record.get("period"))),
            "provenance": deepcopy(record.get("provenance", fact.get("provenance", []))),
            "reported_record": deepcopy(fact),
            "usage": "Candidate input for the declared alternatives; engine calculation details identify the projection used."}
    return records


def enrich_valuation_coverage(inputs, valuation, *, as_of=None):
    """Add explanations to an engine result; preserve every number and decision."""
    result = deepcopy(valuation)
    # Preserve source/presentation metadata without changing engine arithmetic.
    for key in ("original_currency", "currency_resolution", "provider_capabilities", "reporting_currency_compatibility"):
        if key in (inputs.get("market") or {}):
            result.setdefault("market", {})[key] = deepcopy(inputs["market"][key])
    clock = _timestamp(as_of or result.get("calculated_at"))
    if clock is None:
        raise ValueError("Financial coverage requires an explicit zoned audit clock.")
    periods = reporting_periods(inputs)
    checks = compatibility(inputs, result.get("market", {}), clock)
    for case in result.get("scenarios", {}).values():
        for model in case["models"]:
            model["eligibility"]["blockers"] = model_blockers(inputs, model)
        case.setdefault("data_completeness", {}).update(reporting_periods=deepcopy(periods), compatibility=deepcopy(checks))
        case["publication"] = publication_status(inputs, case, checks, clock)
        case["independence"] = build_independence(inputs, case["models"], case["summary"], case["assumptions"])
    base = result["scenarios"]["base"]
    result["data_completeness"] = deepcopy(base["data_completeness"])
    models = base["models"]
    valid = [item for item in models if item["status"] == "valid" and item["eligibility"]["status"] not in {"ineligible", "unavailable"}]
    contributing = set(base["summary"].get("effective_weights", {}))
    families = sorted(group for group, members in GROUPS.items() if contributing.intersection(members))
    company = inputs.get("company", {})
    listing = company.get("listing_verification") or {}
    history = analyze_history(inputs.get("annual_periods", []))
    sufficient = any(history["growth"][key]["3"]["status"] == "available" for key in ("revenue", "eps", "free_cash_flow"))
    assumptions = base["assumptions"].get("metadata", {})
    supported_assumptions = any(
        bool(set(path) & MODEL_ASSUMPTIONS[model["id"]])
        and all(assumptions.get(field, {}).get("value") is not None for field in set(path) & MODEL_ASSUMPTIONS[model["id"]])
        for model in models if model["eligibility"]["status"] != "ineligible"
        for path in required_inputs(model["id"]))
    valid_facts = any(_finite(fact.get("value")) for period in inputs.get("annual_periods", []) for fact in period.get("facts", {}).values())
    stages = {
        "verified_issuer_identity": company.get("identity_status") == "verified" and bool(company.get("cik")),
        "verified_active_listing": company.get("listing_status") == "active" and listing.get("status") == "verified" and listing.get("freshness") == "fresh",
        "security_form": company.get("security_form", company.get("instrument_type")) not in {None, "unknown"},
        "eligible_security_sector": not applicability(company) and any(item["eligibility"]["status"] != "ineligible" for item in models),
        "financial_statements": valid_facts,
        "normalized_metric_completeness": bool(periods) and not periods[0]["missing_metrics"],
        "sufficient_historical_periods": sufficient,
        "compatible_currency_share_basis": checks["share_basis"]["status"] == checks["currency"]["status"] == "available",
        "required_valuation_assumptions": supported_assumptions,
        "at_least_one_eligible_model": bool(valid),
        "fresh_quote": checks["market_price"]["status"] == "available",
        "historical_illustrative_value": base["summary"].get("fair_value") is not None and base["publication"]["result_type"] == "historical_illustration",
        "published_fair_value": base["publication"]["result_type"] == "current_eligible",
    }
    result["financial_coverage"] = {"methodology_version": VERSION, "as_of": clock.isoformat(),
        "publication": deepcopy(base["publication"]),
        "independence": deepcopy(base["independence"]),
        "identity": security_identity(company), "stages": {key: {"status": "available" if value else "unavailable"} for key, value in stages.items()},
        "eligible_model_count": len(valid), "contributing_model_count": base["summary"]["count"],
        "contributing_model_families": families, "reporting_period_count": len(periods),
        "models": [{"id": item["id"], "status": item["status"], "eligibility_status": item["eligibility"]["status"],
            "classification": item.get("classification"), "blockers": deepcopy(item["eligibility"]["blockers"]),
            "input_paths": deepcopy(item["eligibility"].get("input_paths", [])),
            "required_inputs": required_inputs(item["id"]),
            "candidate_input_sources": _candidate_sources(inputs, base["assumptions"], item["id"])}
            for item in models],
        "limitations": ["Coverage stages are independent; unavailable quote/history stages do not modify intrinsic engine outputs.",
            "Metric completeness is an explicit inventory, not a model prerequisite or quality score.",
            "Sufficient history means a supported three-year growth window, not a universal model requirement.",
            "Required assumptions counts an available nonempty forecast/rate/multiple path separately from facts and model suitability; Graham has no numerical forecast assumptions.",
            "Two method families do not establish independent financial evidence; independence remains unverified.",
            "Policy-based and single-model estimates retain their classifications and quality warnings independently of publication currentness."]}
    result["financial_coverage"]["stages"]["at_least_two_independent_model_families"] = {
        "status": "unverified", "reason": "Method families are counted separately; independent financial evidence has not been established."}
    return result


def calculate_with_coverage(inputs, request=None, policy=None):
    return enrich_valuation_coverage(inputs, calculate_valuation(inputs, request, policy))


def summarize_coverage(samples, *, as_of, data_mode):
    """Aggregate only an explicitly bounded, unique, uniformly labeled sample."""
    if data_mode not in {"retained_public", "mocked", "synthetic", "newly_approved_live"}:
        raise ValueError("Explicit financial evidence mode is required.")
    if not 1 <= len(samples) <= 10000 or _timestamp(as_of) is None:
        raise ValueError("A bounded sample and zoned audit timestamp are required.")
    keys = [row["identity"].get("listing_id") for row in samples]
    if any(not key for key in keys) or len(set(keys)) != len(keys):
        raise ValueError("Each sampled security must have its own stable listing identity.")
    if any(row.get("data_mode") != data_mode for row in samples):
        raise ValueError("Different financial evidence modes must not share a denominator.")
    if any(_timestamp(row.get("as_of")) is None or _timestamp(row["as_of"]) > _timestamp(as_of) for row in samples):
        raise ValueError("Sample observations cannot follow the aggregate audit clock.")
    counts = {key: {"numerator": sum(row["stages"][key]["status"] == "available" for row in samples), "denominator": len(samples)}
              for key in samples[0]["stages"]}
    return {"audit_version": VERSION, "as_of": as_of, "data_mode": data_mode,
        "sample_denominator": len(samples), "stages": counts,
        "model_status_counts": {model_id: dict(Counter(next(model for model in row["models"] if model["id"] == model_id)["status"] for row in samples)) for model_id in MODEL_IDS},
        "samples": deepcopy(samples), "limitations": ["This sample does not measure financial coverage for the full registry."]}
