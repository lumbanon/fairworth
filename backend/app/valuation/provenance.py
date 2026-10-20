"""Additive source contract: an estimate never becomes a financial fact."""
from copy import deepcopy

from app.valuation.inputs import day

ASSUMPTION_METHODOLOGY_VERSION = "automatic-assumptions-2"
POLICY_TYPES = {"policy", "benchmark", "benchmark_assumption", "policy_estimate"}
USER_TYPES = {"user", "user_override", "user_assumption"}
FACT_TYPES = {"reported", "reported_input", "market_observation"}
FINANCIAL_FIELDS = {
    "shares": ["weighted_average_diluted_shares"], "debt": ["total_debt"], "cash": ["cash_and_cash_equivalents"],
    "book_equity": ["shareholders_equity"], "revenue_growth": ["revenue"], "forecast_revenue": ["revenue"],
    "earnings_growth": ["diluted_eps", "weighted_average_diluted_shares"], "forward_eps": ["diluted_eps"],
    "cash_flow_growth": ["free_cash_flow"], "operating_margin": ["operating_income", "revenue"],
    "net_margin": ["net_income", "revenue"], "return_on_equity": ["net_income", "shareholders_equity"],
    "payout_ratio": ["dividends_paid", "net_income"], "tax_rate": ["income_tax_expense", "pretax_income"],
    "capex_ratio": ["capital_expenditures", "revenue"], "da_ratio": ["depreciation_and_amortization", "revenue"],
    "ebitda_margin": ["operating_income", "depreciation_and_amortization", "revenue"],
    "forecast_ebitda": ["operating_income", "depreciation_and_amortization", "revenue"],
}


def _financial_sources(inputs, field, period, kind):
    names = FINANCIAL_FIELDS.get(field, [field])
    if kind == "fact":
        candidates = [inputs.get("facts", {})]
    else:
        rows = inputs.get("annual_periods", [])
        start = day(period.get("start", period.get("start_date"))) if isinstance(period, dict) else None
        end = day(period.get("end", period.get("end_date"))) if isinstance(period, dict) else None
        selected = [row for row in rows if (start is None or day(row.get("end_date")) is not None and day(row["end_date"]) >= start)
                    and (end is None or day(row.get("end_date")) is not None and day(row["end_date"]) <= end)]
        candidates = [row.get("facts", {}) for row in selected] or [inputs.get("facts", {})]
    return [source for facts in candidates for name in names for source in facts.get(name, {}).get("provenance", []) if isinstance(source, dict)]


def complete_metadata(record, inputs=None, field=None):
    result = deepcopy(record)
    source_type = result.get("source_type", "unavailable")
    value = result.get("value")
    if source_type in USER_TYPES or result.get("overridden"):
        kind = "user"
    elif source_type in POLICY_TYPES:
        kind = "policy"
    elif value is None:
        kind = "unavailable"
    elif source_type in FACT_TYPES:
        kind = "fact"
    else:
        kind = "estimate"
    result.setdefault("evidence_type", kind)
    result.setdefault("source_category", source_type)
    result.setdefault("source_provider", "User" if kind == "user" else "Fairworth research policy" if kind == "policy" else None)
    if result["source_provider"] is None and inputs and kind != "unavailable":
        references = inputs.get("source_references", [])
        providers = sorted({str(item["provider"]) for item in references if item.get("provider")})
        # Financial history is SEC evidence, not the quote provider used elsewhere.
        result["source_provider"] = "sec-edgar" if any("sec" in p.lower() for p in providers) else ", ".join(providers) or None
    period = result.get("financial_period", result.get("observation_period"))
    if kind in {"user", "policy"}:
        period = result.get("financial_period")
    result.setdefault("financial_period", deepcopy(period))
    result.setdefault("observation_date", None)
    result.setdefault("derivation_formula", result.get("derivation_method"))
    result.setdefault("source_identifiers", [])
    if inputs and kind in {"fact", "estimate"} and not result["source_identifiers"]:
        provenance = _financial_sources(inputs, field, period, kind)
        identifiers = sorted({source["accn"] for source in provenance if source.get("accn")})
        result["source_identifiers"] = identifiers
        dates = [day(source.get("filed")) for source in provenance]
        dates = [observed for observed in dates if observed is not None]
        if dates and result["observation_date"] is None:
            result["observation_date"] = max(dates).isoformat()
    warnings = result.get("warnings", [])
    result.setdefault("quality", {"level": "review_required" if warnings or kind in {"estimate", "policy", "user"} else "reported" if kind == "fact" else "unavailable",
                                  "warnings": deepcopy(warnings)})
    result.setdefault("editable", True)
    # This state describes raw financial inputs. It does not certify estimates.
    result.setdefault("input_status", "user_supplied" if kind == "user" else "verified_zero" if kind == "fact" and value == 0 else "verified_value" if kind == "fact" and value is not None else "unknown" if value is None else None)
    result.setdefault("methodology_version", ASSUMPTION_METHODOLOGY_VERSION)
    return result


def complete_assumptions(assumptions, inputs=None):
    result = deepcopy(assumptions)
    result["metadata"] = {field: complete_metadata(record, inputs, field) for field, record in result.get("metadata", {}).items()}
    result["methodology_version"] = ASSUMPTION_METHODOLOGY_VERSION
    return result
