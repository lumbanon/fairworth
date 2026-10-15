"""Transparent additional forecasts supported by new, verified evidence.

This module does not replace Phase 4 defaults when no new evidence exists. It
returns estimates with explicit dependencies, never edits reported facts, and
never substitutes ordinary reported free cash flow for FCFF or FCFE.
"""

from __future__ import annotations

from copy import deepcopy
import math
from statistics import median, pstdev

from app.valuation.historical_multiples import _adjusted_eps, _facts, _publication, _valid_period
from app.valuation.history import _aligned, historical_cagr
from app.valuation.inputs import day, number

METHODOLOGY_VERSION = "automatic-forward-forecasts-1"


def _setting(policy, key, default):
    return policy.get(key, default) if isinstance(policy, dict) else getattr(policy, key, default)


def _warning(field, code, message):
    return {"field": field, "code": code, "message": message}


def _record(value, unit, description, formula, periods, warnings=(), dependencies=(), policies=(), **extra):
    return {"value": value, "unit": unit, "source_type": "derived_estimate", "source_category": "derived_historical_estimate",
            "source_provider": "sec-edgar", "source_description": description, "derivation_method": formula,
            "derivation_formula": formula, "observation_date": max((str(record.get("filed", "")) for period in periods for fact in period.get("facts", {}).values()
                                                                       for record in fact.get("provenance", []) if record.get("filed")), default=None),
            "observation_period": {"start": periods[0]["end_date"], "end": periods[-1]["end_date"]} if periods else None,
            "financial_period": {"fiscal_years": [period["fiscal_year"] for period in periods]},
            "warnings": list(warnings), "evidence_type": "estimate", "quality": "low" if policies else "moderate",
            "editable": True, "overridden": False, "dependency_fields": list(dependencies), "policy_dependencies": list(policies),
            "source_identifiers": sorted({str(record.get("accn")) for period in periods for fact in period.get("facts", {}).values()
                                         for record in fact.get("provenance", []) if record.get("accn")}),
            "fill_only": True, **extra}


def revenue_path(revenue, initial_growth, terminal_growth, forecast_years, fade=True):
    """Annual revenue in absolute units; same linear fade convention as Phase 4."""
    revenue, initial_growth, terminal_growth = number(revenue), number(initial_growth), number(terminal_growth)
    if (revenue is None or revenue <= 0 or initial_growth is None or not -0.99 < initial_growth <= 2
            or terminal_growth is None or not -0.5 <= terminal_growth <= 0.15
            or type(forecast_years) is not int or not 1 <= forecast_years <= 30 or type(fade) is not bool):
        raise ValueError("Revenue paths require positive finite revenue, valid growth, a bounded integer horizon, and a boolean fade policy.")
    result = []
    amount = revenue
    for year in range(1, forecast_years + 1):
        rate = initial_growth + (terminal_growth - initial_growth) * (year - 1) / (forecast_years - 1) if fade and forecast_years > 1 else initial_growth
        amount *= 1 + rate
        if not math.isfinite(amount) or amount <= 0:
            raise ValueError("The selected growth and horizon do not produce finite positive annual revenue.")
        result.append(amount)
    return result


def _growth_estimate(periods, field, policy, requested=None):
    choices = (int(requested),) if requested is not None and not isinstance(requested, bool) and requested in (3, 5, 10) else (5, 3)
    if requested is not None and (isinstance(requested, bool) or requested not in (3, 5, 10)):
        return None, None
    available = [(years, historical_cagr(periods, field, years)) for years in choices]
    chosen = next(((years, result) for years, result in available if result["status"] == "available"), None)
    if chosen is None:
        return None, None
    years, result = chosen
    window = periods[-(years + 1):]
    changes = result["annual_growth"]
    # Deceleration is visible: take the lesser of the long-window CAGR, recent
    # three-year CAGR, latest YoY, and recent median YoY. No opaque scoring.
    recent = historical_cagr(periods, field, 3)
    candidates = [result["value"], changes[-1], median(changes[-3:])]
    if recent["status"] == "available":
        candidates.append(recent["value"])
    raw = min(candidates)
    minimum = _setting(policy, "minimum_forecast_growth", -0.15)
    maximum = _setting(policy, "maximum_forecast_growth", 0.20)
    used = max(minimum, min(maximum, raw))
    warnings = list(result.get("warnings", []))
    policies = ["historical_growth_deceleration_rule"]
    if used != raw:
        policies.append("historical_forecast_growth_bounds")
        warnings.append(_warning(field, "historical_growth_policy_bounded", "The transparent historical growth estimate is bounded by an editable forecasting policy; extraordinary growth is not projected indefinitely."))
    if max(changes) - min(changes) > _setting(policy, "maximum_annual_growth_dispersion", 1):
        warnings.append(_warning(field, "variable_growth_requires_caution", "Historical annual growth is highly variable; the conservative bounded forecast is illustrative and is not an analyst consensus estimate."))
    if changes[-1] < -0.5:
        return None, {"status": "unavailable", "reason": "recent_fundamental_collapse", "years": years}
    details = {"status": "available", "lookback_years": years, "raw_cagr": result["value"],
               "recent_three_year_cagr": recent["value"], "latest_year_over_year": changes[-1],
               "recent_median_year_over_year": median(changes[-3:]), "raw_conservative_growth": raw,
               "used_growth": used, "annual_growth_volatility": pstdev(changes), "growth_candidates": candidates,
               "historical_periods": [period["fiscal_year"] for period in window]}
    record = _record(used, "fraction", "Conservative forecast from verified comparable original annual financial history; not a reported forward estimate.",
                     "min(window CAGR, recent three-year CAGR, latest YoY, median latest three YoY), then disclosed configurable growth bounds.",
                     window, warnings, dependencies=("lookback_years",), policies=policies, lookback_years=years,
                     historical_analytics=details)
    return record, details


def _published_periods(evidence, currency, as_of):
    periods = []
    for original in evidence.get("historical_annual_periods", []):
        if not isinstance(original, dict) or not _valid_period(original, currency):
            continue
        period = deepcopy(original)
        for field, fact in period.get("facts", {}).items():
            known = _publication([fact])
            if known is None or known > as_of or number(fact.get("value")) is None:
                period.setdefault("metrics", {})[field] = None
        periods.append(period)
    # Original evidence is one native annual publication per year. Ambiguous
    # duplicate periods are handled by the existing history selection rules.
    from app.valuation.history import select_annual_periods
    selected, _ = select_annual_periods(periods)
    return selected


def _ratios(periods, amount_field, revenue_field="revenue"):
    window = periods[-3:]
    if len(window) != 3 or any(not _aligned(left, right) for left, right in zip(window, window[1:])):
        return None, []
    result = []
    for period in window:
        revenue, revenue_fact = _facts(period, (revenue_field,))
        amount, amount_fact = _facts(period, (amount_field,))
        if (revenue is None or revenue <= 0 or amount is None or amount_fact.get("unit") != period["currency"]
                or revenue_fact.get("unit") != period["currency"] or not math.isfinite(amount / revenue)):
            return None, []
        result.append(amount / revenue)
    return median(result), window


def _working_capital(periods, as_of, currency):
    rows = []
    fields = ("operating_current_assets", "operating_current_liabilities")
    for period in periods:
        if not _valid_period(period, currency):
            continue
        facts, values = [], []
        for field in fields:
            value, fact = _facts(period, (field,))
            if value is None or value < 0 or fact.get("scope_complete") is not True or fact.get("unit") != currency:
                break
            values.append(value)
            facts.append(fact)
        if len(values) != 2 or _publication(facts) is None or _publication(facts) > as_of:
            continue
        revenue, _ = _facts(period, ("revenue",))
        if revenue is not None and revenue > 0:
            rows.append({**period, "operating_nwc": values[0] - values[1], "nwc_ratio": (values[0] - values[1]) / revenue})
    rows.sort(key=lambda period: period["fiscal_year"])
    window = rows[-3:]
    if len(window) != 3 or any(not _aligned(left, right) for left, right in zip(window, window[1:])):
        return {}
    ratio = median([row["nwc_ratio"] for row in window])
    if not math.isfinite(ratio) or not -2 <= ratio <= 2:
        return {}
    return {"nwc_ratio": _record(ratio, "fraction", "Median of three complete, aligned noncash operating working-capital/revenue observations; financing liabilities, cash and investments are excluded by explicit source scope.",
                                 "median((verified operating current assets - verified operating current liabilities) / reported revenue)", window,
                                 policies=("constant_operating_nwc_ratio",)),
            "change_nwc": _record(window[-1]["operating_nwc"] - window[-2]["operating_nwc"], currency,
                                   "Latest reported change in complete noncash operating working capital; not ordinary reported OCF or FCF.",
                                   "operating NWC at latest fiscal year end - prior aligned fiscal year end", window[-2:])}


def _net_borrowing(periods, as_of, currency):
    usable = []
    for period in periods:
        if not _valid_period(period, currency):
            continue
        issued, issued_fact = _facts(period, ("debt_issuance",))
        repaid, repaid_fact = _facts(period, ("debt_principal_repayments",))
        facts = [issued_fact, repaid_fact]
        if (issued is None or repaid is None or issued < 0 or repaid < 0
                or any(fact.get("scope_complete") is not True or fact.get("unit") != currency for fact in facts)
                or _publication(facts) is None or _publication(facts) > as_of):
            continue
        usable.append({**period, "net_borrowing": issued - repaid})
    usable.sort(key=lambda period: period["fiscal_year"])
    window = usable[-3:]
    if len(window) != 3 or any(not _aligned(left, right) for left, right in zip(window, window[1:])):
        return None
    flows = [period["net_borrowing"] for period in window]
    if min(flows) < 0 < max(flows):
        return None
    value = median(flows)
    if not math.isfinite(value):
        return None
    return _record(value, currency, "Median of three complete annual financing-flow observations; a disclosed borrowing forecast assumption, not a current financing commitment.",
                   "median(reported complete debt issuance proceeds - reported principal debt repayments); never change in debt balance.", window,
                   [_warning("net_borrowing", "financing_history_is_not_a_commitment", "Future borrowing and repayments may differ; analyst financing projections are preferred.")],
                   policies=("constant_annual_net_borrowing",))


def derive_forward_forecasts(inputs, evidence, policy=None, *, overrides=None):
    """Return optional estimates; explicit edits win and dependencies are disclosed."""
    evidence = evidence or {}
    if not evidence.get("historical_annual_periods"):
        return {"assumptions": {}, "forecast_quality": {"status": "unavailable", "reason": "no_new_verified_historical_evidence"},
                "warnings": [], "methodology_version": METHODOLOGY_VERSION}
    overrides = overrides or {}
    as_of = day(evidence.get("as_of_date")) or day(str(inputs.get("financial_retrieved_at") or "")[:10])
    as_of = as_of or day(str((evidence.get("historical_prices") or {}).get("retrieved_at") or "")[:10])
    if as_of is None:
        return {"assumptions": {}, "forecast_quality": {"status": "unavailable", "reason": "missing_snapshot_date"},
                "warnings": [], "methodology_version": METHODOLOGY_VERSION}
    currency = inputs.get("currency")
    periods = _published_periods(evidence, currency, as_of)
    records, quality = {}, {"status": "available", "historical_periods": [period["fiscal_year"] for period in periods],
                           "normalization_adjustments": "No undisclosed one-time-item adjustments; margins use comparable historical medians.",
                           "growth_convergence": "Linearly fades initial revenue growth toward explicit terminal growth when enabled.",
                           "limitations": ["Derived forecasts are estimates, not verified analyst consensus.", "Historical financing and reinvestment patterns may change."]}
    if not periods:
        quality.update(status="unavailable", reason="no_compatible_annual_observations")
        return {"assumptions": {}, "forecast_quality": quality, "warnings": [], "methodology_version": METHODOLOGY_VERSION}
    revenue_growth, growth_details = _growth_estimate(periods, "revenue", policy, overrides.get("lookback_years"))
    quality["revenue_growth"] = growth_details
    if revenue_growth:
        records["revenue_growth"] = revenue_growth
    share_verified = inputs.get("basis", {}).get("share_basis_verified") is True
    synthetic_price = {"date": as_of.isoformat(), "close": 1, "adjustment_basis": "split_adjusted", "adjustment_date": as_of.isoformat()}
    adjusted_periods = deepcopy(periods)
    if share_verified:
        for period in adjusted_periods:
            adjusted, error = _adjusted_eps(period, synthetic_price, evidence.get("splits") or {})
            period.setdefault("metrics", {})["diluted_eps"] = adjusted
            if adjusted is not None:
                # History's split-discontinuity guard sees an explicitly common
                # split basis instead of incompatible original share counts.
                original = number(period["metrics"].get("weighted_average_diluted_shares"))
                raw_eps = number(period["facts"].get("diluted_eps", {}).get("value"))
                if original is not None and original > 0 and raw_eps is not None and adjusted > 0:
                    period["metrics"]["weighted_average_diluted_shares"] = original * raw_eps / adjusted
            if error:
                quality.setdefault("earnings_basis_warnings", []).append({"fiscal_year": period["fiscal_year"], "code": error})
        earnings, details = _growth_estimate(adjusted_periods, "diluted_eps", policy, overrides.get("lookback_years"))
        if earnings:
            earnings["source_description"] = "Conservative growth forecast from explicitly split-adjusted original reported diluted EPS on the selected quoted-class basis."
            earnings["derivation_method"] += " Original EPS is first divided by verified subsequent split factors."
            earnings["derivation_formula"] = earnings["derivation_method"]
            records["earnings_growth"] = earnings
        quality["earnings_growth"] = details
    for key, field in (("operating_margin", "operating_income"), ("net_margin", "net_income"), ("capex_ratio", "capital_expenditures"), ("da_ratio", "depreciation_and_amortization")):
        if key == "net_margin" and not inputs.get("basis", {}).get("income_earnings_basis_verified"):
            continue
        ratio, window = _ratios(periods, field)
        if ratio is not None and (-2 <= ratio <= 2 if "margin" in key else 0 <= ratio <= 3):
            records[key] = _record(ratio, "fraction", "Median of three compatible annual reported ratios; a normalized forecasting estimate without invented company adjustments.",
                                   f"median({field} / revenue) over three aligned fiscal years", window)
    ebitda_rows = []
    for period in periods:
        ebit, ebit_fact = _facts(period, ("operating_income",))
        da, da_fact = _facts(period, ("depreciation_and_amortization",))
        if ebit is not None and da is not None and da >= 0 and ebit_fact.get("unit") == currency and da_fact.get("unit") == currency and math.isfinite(ebit + da):
            period = deepcopy(period)
            period["metrics"]["ebitda"] = ebit + da
            period["facts"]["ebitda"] = {"value": ebit + da, "unit": currency, "provenance": [*ebit_fact["provenance"], *da_fact["provenance"]]}
            ebitda_rows.append(period)
    ebitda_margin, window = _ratios(ebitda_rows, "ebitda")
    if ebitda_margin is not None and 0 < ebitda_margin <= 2:
        records["ebitda_margin"] = _record(ebitda_margin, "fraction", "Median of three compatible EBIT-plus-D&A/revenue observations; operating income is an identified EBIT proxy.",
                                          "median((reported operating income + compatible reported D&A) / revenue)", window,
                                          [_warning("ebitda_margin", "operating_income_ebit_proxy", "Company-specific nonoperating and EBITDA adjustments are not fabricated.")])
    records.update(_working_capital(evidence.get("operating_working_capital_periods", []), as_of, currency))
    borrowing = _net_borrowing(evidence.get("financing_periods", []), as_of, currency)
    if borrowing:
        records["net_borrowing"] = borrowing
    # Overrides here affect pure forecasts only. Root assumption orchestration
    # records their user provenance and keeps reset values separate.
    def selected(key):
        return overrides[key] if key in overrides else records.get(key, {}).get("value")
    initial_growth = number(selected("revenue_growth"))
    base = number(inputs.get("values", {}).get("revenue"))
    count = overrides.get("forecast_years", _setting(policy, "forecast_years", 5))
    if isinstance(count, float) and count.is_integer():
        count = int(count)
    terminal = overrides.get("terminal_growth", _setting(policy, "terminal_growth", 0.02))
    fade = overrides.get("growth_fade_to_terminal", True)
    if base is not None and initial_growth is not None:
        try:
            path = revenue_path(base, initial_growth, terminal, count, fade)
        except ValueError as error:
            quality["revenue_path_error"] = str(error)
        else:
            records["projected_revenue"] = _record(path, f"{currency}/year", "Year-by-year revenue forecast from a verified annual base and disclosed growth convergence; no observed future revenue is claimed.",
                                                    "Revenue[t] = Revenue[t-1] × (1 + growth[t]); growth fades linearly from initial growth toward terminal growth.", periods[-1:],
                                                    dependencies=("revenue_growth", "terminal_growth", "forecast_years", "growth_fade_to_terminal"),
                                                    policies=("linear_growth_convergence",), computed_only=True)
            records["forecast_revenue"] = _record(path[0], currency, "One-year revenue forecast; distinct from trailing reported revenue.",
                                                   "reported annual revenue × (1 + forecast revenue growth)", periods[-1:],
                                                   dependencies=("revenue_growth",), computed_only=True)
            margin = number(selected("ebitda_margin"))
            if margin is not None and margin > 0 and math.isfinite(path[0] * margin):
                records["forecast_ebitda"] = _record(path[0] * margin, currency, "One-year revenue forecast multiplied by a compatible normalized EBITDA-margin estimate.",
                                                    "forecast revenue × normalized EBITDA margin", periods[-3:],
                                                    dependencies=("revenue_growth", "ebitda_margin", "forecast_revenue"), computed_only=True)
    earnings_growth = number(selected("earnings_growth"))
    latest_eps = adjusted_periods[-1]["metrics"].get("diluted_eps") if share_verified else None
    if number(latest_eps) is not None and latest_eps > 0 and earnings_growth is not None and math.isfinite(latest_eps * (1 + earnings_growth)):
        records["forward_eps"] = _record(latest_eps * (1 + earnings_growth), f"{currency}/shares",
                                         "One-year EPS forecast from verified split-compatible reported diluted EPS and a disclosed earnings-growth estimate.",
                                         "split-compatible reported diluted EPS × (1 + forecast earnings growth)", periods[-1:],
                                         dependencies=("earnings_growth",), computed_only=True)
    quality["input_completeness"] = {"compatible_eps_forecast": "forward_eps" in records,
                                    "compatible_ebitda_forecast": "forecast_ebitda" in records,
                                    "complete_operating_working_capital": "nwc_ratio" in records,
                                    "complete_financing_forecast": "net_borrowing" in records}
    return {"assumptions": records, "forecast_quality": quality, "warnings": [], "methodology_version": METHODOLOGY_VERSION}
