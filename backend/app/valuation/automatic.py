"""Snapshot-only evidence integration, with no network or user-fact persistence."""
from copy import deepcopy
from datetime import date
import math

from app.valuation.assumptions import estimate_cost_of_equity, estimate_wacc
from app.valuation.inputs import _fact, day, number
from app.valuation.history import _aligned
from app.valuation.provenance import complete_metadata

AMOUNT_OBSERVATIONS = {"debt", "cash", "preferred_equity", "minority_interest", "other_nonoperating_assets", "depreciation_and_amortization"}
CLAIMS = {"preferred_equity", "minority_interest", "other_nonoperating_assets"}


def observation_metadata(record):
    result = deepcopy(record)
    result["evidence_type"] = result.get("kind", "unavailable" if result.get("value") is None else "estimate")
    result["input_status"] = result.get("state", "unknown")
    result.setdefault("financial_period", result.get("period"))
    result.setdefault("observation_period", result.get("period"))
    result.setdefault("derivation_method", result.get("derivation_formula") or result.get("methodology"))
    result.setdefault("source_identifiers", [result["source_id"]] if result.get("source_id") else [])
    result.setdefault("source_provider", result.get("provider"))
    return complete_metadata(result)


def usable_observation(record, *, unit=None):
    observed = day(str(record.get("observation_date") or "")[:10])
    value = number(record.get("value"))
    return (value is not None and observed is not None and observed <= date.today()
            and record.get("state") in {"verified_value", "verified_zero"}
            and bool(record.get("source_provider") or record.get("provider"))
            and (unit is None or record.get("unit") == unit))


def compatible_statement_observation(record, inputs, field):
    """Do not overwrite a financial baseline with a different-period fact."""
    selected = inputs.get("reporting_period") or {}
    if field == "debt":
        # Re-check the original validated baseline as well as its diagnostic.
        # Cached/API periods can omit their redundant currency field; they
        # must not lose a conflict when the dataset provides that currency.
        from app.services.normalization import reconcile_debt_evidence
        baseline_facts = inputs.get("facts", {})
        baseline = {**selected, "currency": inputs.get("currency"),
                    "metrics": {key: fact.get("value") for key, fact in baseline_facts.items() if isinstance(fact, dict)},
                    "provenance": {key: fact.get("provenance", []) for key, fact in baseline_facts.items() if isinstance(fact, dict)}}
        if (inputs.get("financial_reconciliations", {}).get("debt", {}).get("status") == "conflict"
                or reconcile_debt_evidence(baseline)["status"] == "conflict"):
            # Another observation of one candidate cannot resolve competing
            # same-period debt disclosures in the annual baseline.
            return False
    selected_end = day(selected.get("end_date"))
    period = record.get("period") or record.get("financial_period") or {}
    declared_end = day(period.get("end_date", period.get("end"))) if isinstance(period, dict) else None
    observed = day(str(record.get("observation_date") or "")[:10])
    if selected_end is None or observed != selected_end or declared_end not in (None, selected_end):
        return False
    duration = field == "depreciation_and_amortization"
    if duration and (not isinstance(period, dict) or day(period.get("start_date", period.get("start"))) != day(selected.get("start_date"))):
        return False
    provenance = record.get("provenance")
    sec_source = "sec" in str(record.get("source_provider") or record.get("provider") or "").lower() or any(
        isinstance(source, dict) and source.get("source") == "sec" for source in provenance or [])
    if field == "debt" and not sec_source and record.get("scope_complete") is not True:
        return False
    if provenance:
        metric = "total_debt" if field == "debt" else "cash_and_cash_equivalents" if field == "cash" else field
        checked = _fact(metric, record.get("value"), {**selected, "currency": inputs.get("currency"), "provenance": {metric: provenance}}, inputs.get("currency"), record.get("retrieved_at"))
        return checked["value"] is not None
    # Explicit source IDs can support additional non-SEC verified disclosures;
    # a provider label alone cannot establish a fact's original identity.
    if "sec" in str(record.get("source_provider") or record.get("provider") or "").lower():
        return False
    return bool(record.get("source_id") or record.get("source_identifiers"))


def cost_of_debt_from_history(periods):
    """A historical financing-cost proxy, never presented as a bond yield."""
    result = {"value": None, "unit": "fraction", "source_type": "unavailable", "evidence_type": "unavailable",
              "warnings": ["Compatible annual interest expense and two complete dated debt balances are required; missing debt is not zero."], "editable": False}
    if len(periods) < 2:
        return result
    previous, latest = sorted(periods, key=lambda row: row.get("end_date", ""))[-2:]
    if not _aligned(previous, latest):
        return result
    values = [number(previous.get("metrics", {}).get("total_debt")), number(latest.get("metrics", {}).get("total_debt")), number(latest.get("metrics", {}).get("interest_expense"))]
    if any(value is None or value <= 0 for value in values):
        return result
    facts = [previous.get("facts", {}).get("total_debt"), latest.get("facts", {}).get("total_debt"), latest.get("facts", {}).get("interest_expense")]
    if any(not fact or fact.get("unit") != latest.get("currency") or fact.get("warnings") or not fact.get("provenance") for fact in facts):
        return result
    average = (values[0] + values[1]) / 2
    rate = values[2] / average
    if not math.isfinite(rate) or not 0 < rate <= 0.5:
        return result
    publications = [day(record.get("filed")) for fact in facts for record in fact["provenance"]]
    if any(observed is None or observed > date.today() for observed in publications):
        return result
    method = "Annual reported interest expense / arithmetic average of beginning and ending complete book debt; historical financing-cost proxy, not a current market borrowing yield."
    return {"value": rate, "unit": "fraction", "source_type": "derived_estimate", "evidence_type": "estimate",
            "source_provider": "sec-edgar", "source_description": method, "derivation_method": method,
            "derivation_formula": "interest_expense / ((beginning_total_debt + ending_total_debt) / 2)",
            "observation_date": max(publications).isoformat(), "financial_period": {"start": latest["start_date"], "end": latest["end_date"]},
            "inputs": {"interest_expense": values[2], "beginning_total_debt": values[0], "ending_total_debt": values[1]},
            "source_identifiers": sorted({record["accn"] for fact in facts for record in fact["provenance"] if record.get("accn")}),
            "warnings": ["Expense scope, capitalized interest, debt timing and contractual rates may differ from today's marginal borrowing cost; automatic WACC does not silently treat this as a market yield."], "editable": False}


def prepare_automatic_inputs(inputs, evidence, policy=None):
    """Retain official facts; expose validated additional inputs and analytics."""
    from app.valuation.historical_multiples import derive_historical_multiples
    from app.valuation.forecasts import derive_forward_forecasts

    result = deepcopy(inputs)
    result["automatic_evidence"] = deepcopy(evidence)
    if not evidence:
        return result
    observations = evidence.get("observations", {})
    records = {key: observation_metadata(value) for key, value in observations.items() if isinstance(value, dict)}
    as_of = day(evidence.get("as_of_date"))
    def within_snapshot(record):
        observed = day(str(record.get("observation_date") or "")[:10])
        return as_of is None or observed is not None and observed <= as_of
    for key in AMOUNT_OBSERVATIONS:
        record = observations.get(key, {})
        valid = (usable_observation(record, unit=result.get("currency")) and number(record.get("value")) >= 0
                 and compatible_statement_observation(record, result, key) and within_snapshot(record))
        valid = valid and (key not in CLAIMS or record.get("scope_complete") is True)
        valid = valid and (key not in CLAIMS or record.get("value") != 0 or record.get("state") == "verified_zero")
        if not valid:
            if key in records:
                state = ("unknown" if key in CLAIMS and record.get("scope_complete") is not True
                         else record.get("state") if record.get("state") in {"unknown", "unavailable"} else "unavailable")
                records[key].update(value=None, reported_value=number(record.get("value")), reported_input_status=record.get("state"),
                                    input_status=state, source_type="unavailable", evidence_type="unavailable")
                records[key].setdefault("warnings", []).append("Unit, date, availability or complete claim scope does not support use as a valuation input.")
            continue
        result["values"][key] = record["value"]
    current = observations.get("current_shares", {})
    current_usable = usable_observation(current, unit="shares") and within_snapshot(current) and current.get("scope_verified") is True and current["value"] > 0
    if current_usable:
        result["values"]["shares"] = current["value"]
        records["shares"] = observation_metadata(current)
        result["basis"]["valuation_share_denominator"] = current.get("share_basis")
        result["basis"]["valuation_share_observation_date"] = current.get("observation_date")
    elif "current_shares" in records:
        records["current_shares"].update(value=None, reported_value=number(current.get("value")),
                                         source_type="unavailable", evidence_type="unavailable", input_status="unavailable")
        records["current_shares"].setdefault("warnings", []).append("The dated share observation has no compatible verified common-share scope or falls outside this snapshot.")
    # Keep reported annual EPS separate from dated current/period-end shares.
    # The existing common-income compatibility flag is never recomputed here.
    multiples = derive_historical_multiples(result, evidence, policy)
    forecasts = derive_forward_forecasts(result, evidence, policy)
    records.update(multiples.get("assumptions", {}))
    records.update(forecasts.get("assumptions", {}))
    debt_cost = cost_of_debt_from_history(result.get("annual_periods", []))
    records["cost_of_debt"] = debt_cost
    result["automatic_assumptions"] = records
    result["automatic_analytics"] = {"historical_multiples": multiples.get("statistics", {}), "forecast_quality": forecasts.get("forecast_quality", {}),
                                     "historical_methodology_version": multiples.get("methodology_version"), "forecast_methodology_version": forecasts.get("methodology_version")}
    return result


def automatic_discount_records(inputs, defaults, explicit=None):
    """Partial evidence leaves the disclosed policy rate intact, never beta=1."""
    observations = inputs.get("automatic_evidence", {}).get("observations", {})
    if not observations:
        return defaults
    def rate(key):
        record = observations.get(key, {})
        if not usable_observation(record):
            return None
        as_of = day(inputs.get("automatic_evidence", {}).get("as_of_date"))
        if as_of is not None and day(str(record.get("observation_date") or "")[:10]) > as_of:
            return None
        return {**record, "source": record.get("source_provider") or record.get("provider"),
                "method": record.get("methodology") or record.get("derivation_formula") or record.get("source_description")}
    try:
        ke = estimate_cost_of_equity(rate("risk_free_rate"), rate("beta"), rate("equity_risk_premium"))
    except (ValueError, TypeError) as error:
        defaults["metadata"]["cost_of_equity"].setdefault("warnings", []).append(str(error))
        return defaults
    erp = observations.get("equity_risk_premium", {})
    policy = erp.get("kind") == "policy" or erp.get("source_type") == "policy"
    ke.update(evidence_type="policy" if policy else "estimate", source_provider="CAPM sourced inputs",
              policy_dependencies=["equity_risk_premium"] if policy else [], dependency_fields=["risk_free_rate", "beta", "equity_risk_premium"],
              observation_date=max(str(observations[k]["observation_date"])[:10] for k in ("risk_free_rate", "beta", "equity_risk_premium")), editable=True, overridden=False, default_value=ke["value"])
    defaults["values"]["cost_of_equity"] = ke["value"]
    defaults["metadata"]["cost_of_equity"] = complete_metadata(ke, inputs, "cost_of_equity")
    # A current market debt observation is required. Book-debt proxies are only
    # available through the existing explicit, disclosed request opt-in.
    debt = observations.get("debt_market_value")
    debt_cost = rate("cost_of_debt")
    market = inputs.get("market") or {}
    if debt is None or debt_cost is None or market.get("market_cap") is None:
        return defaults
    equity = {"value": market["market_cap"], "source": market.get("provider"), "observation_date": str(market.get("price_timestamp", ""))[:10], "currency": market.get("currency"), "basis": "market_value"}
    try:
        wacc = estimate_wacc((explicit or {}).get("cost_of_equity", ke["value"]), debt_cost, defaults["values"].get("tax_rate"), equity, debt)
    except (ValueError, TypeError):
        return defaults
    wacc.update(evidence_type=ke["evidence_type"], policy_dependencies=ke["policy_dependencies"], dependency_fields=["cost_of_equity", "cost_of_debt", "tax_rate"], editable=True, overridden=False, default_value=wacc["value"])
    defaults["values"]["wacc"] = wacc["value"]
    defaults["metadata"]["wacc"] = complete_metadata(wacc, inputs, "wacc")
    return defaults
