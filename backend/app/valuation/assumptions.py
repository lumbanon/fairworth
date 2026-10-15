"""Transparent history-based estimates and explicitly illustrative policy defaults.

No current risk-free rate, beta, cost of debt, or valuation multiple is invented.
Default policy numbers are editable modeling assumptions, not observed facts.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from statistics import median
from typing import Any

from app.valuation.history import analyze_history
from app.valuation.inputs import day, number
from app.valuation.provenance import complete_assumptions

METHODOLOGY_SOURCES = {
    "stable_growth": "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/valquestions/stablegrowthrate.htm",
    "cash_flows": "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/littlebook/cashflows.htm",
    "relative_valuation": "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/background/valintro.htm",
}


@dataclass(frozen=True)
class AssumptionPolicy:
    """Fairworth illustrative policy v1; these numbers are not market observations."""

    version: str = "illustrative-policy-1"
    forecast_years: int = 5
    terminal_growth: float = 0.02
    cost_of_equity: float = 0.10
    minimum_forecast_growth: float = -0.15
    maximum_forecast_growth: float = 0.20
    maximum_annual_growth_dispersion: float = 1.0
    historical_multiple_years: int = 5
    historical_multiple_minimum_years: int = 3
    allow_benchmark_cost_of_equity: bool = True


BASE_UNITS = {
    "revenue_growth": "fraction", "earnings_growth": "fraction", "cash_flow_growth": "fraction",
    "operating_margin": "fraction", "ebitda_margin": "fraction", "terminal_growth": "fraction",
    "wacc": "fraction", "cost_of_equity": "fraction", "target_pe": "multiple",
    "target_ev_ebitda": "multiple", "target_ev_revenue": "multiple", "target_peg": "multiple",
    "target_pb": "multiple", "target_p_affo": "multiple", "forecast_years": "years",
    "dividend_growth": "fraction", "return_on_equity": "fraction", "payout_ratio": "fraction",
    "terminal_roe": "fraction", "capex_ratio": "fraction", "da_ratio": "fraction", "nwc_ratio": "fraction",
    "tax_rate": "fraction", "share_basis_confirmed": "boolean", "book_value_meaningful": "boolean",
    "clean_surplus_confirmed": "boolean", "stable_dividend_confirmed": "boolean",
    "is_bank": "boolean", "is_reit": "boolean", "shares": "shares",
    "risk_free_rate": "fraction", "beta": "ratio", "equity_risk_premium": "fraction",
    "cost_of_debt": "fraction", "reinvestment_rate": "fraction", "net_income_growth": "fraction",
    "net_margin": "fraction", "growth_fade_to_terminal": "boolean", "affo_basis_confirmed": "boolean",
    "common_equity_basis_confirmed": "boolean",
    "lookback_years": "fiscal_years",
}


def _metadata(value=None, unit=None, source_type="unavailable", source_description="No defensible default is available; explicit analyst input is required.", observation_period=None, derivation_method=None, warnings=None, overridden=False):
    return {"value": value, "unit": unit, "source_type": source_type,
            "source_description": source_description, "observation_period": observation_period,
            "derivation_method": derivation_method, "editable": True, "overridden": overridden,
            "warnings": list(warnings or [])}


def _warning(field: str, code: str, message: str) -> dict:
    return {"field": field, "code": code, "message": message}


def _policy(policy) -> AssumptionPolicy:
    candidate = policy if isinstance(policy, AssumptionPolicy) else AssumptionPolicy(**(policy or {}))
    if (not 1 <= candidate.forecast_years <= 20 or not -0.05 <= candidate.terminal_growth <= 0.05
            or not 0 < candidate.cost_of_equity <= 0.5
            or not -0.99 < candidate.minimum_forecast_growth <= candidate.maximum_forecast_growth <= 1
            or not 0 <= candidate.maximum_annual_growth_dispersion <= 5
            or not 3 <= candidate.historical_multiple_years <= 10
            or not 3 <= candidate.historical_multiple_minimum_years <= 10):
        raise ValueError("Illustrative policy values are outside supported modeling bounds.")
    return candidate


def generate_assumptions(inputs: dict, overrides: dict | None = None, policy=None) -> dict:
    """Resolve assumptions in declared hierarchy without mutating facts or snapshots."""
    chosen_policy = _policy(policy)
    history = analyze_history(inputs.get("annual_periods", []))
    metadata = {key: _metadata(unit=unit) for key, unit in BASE_UNITS.items()}
    currency = inputs.get("currency")
    for key in ("forward_eps", "book_value_per_share", "dividend_per_share", "forward_affo_per_share"):
        metadata[key] = _metadata(unit=f"{currency}/shares" if currency else "currency/shares")
    for key in ("forecast_revenue", "forecast_ebitda", "fcff", "fcfe", "net_borrowing", "change_nwc", "preferred_equity", "minority_interest", "other_nonoperating_assets", "debt", "cash", "book_equity", "affo", "forecast_affo"):
        metadata[key] = _metadata(unit=currency)
    for key in ("projected_fcff", "projected_fcfe", "projected_dividends", "projected_revenue"):
        metadata[key] = _metadata(unit=f"{currency}/shares/year" if key == "projected_dividends" else f"{currency}/year" if currency else "currency/year")

    def set_value(key, value, source_type, description, method=None, period=None, warnings=None):
        if not isinstance(value, bool) and value is not None and number(value) is None:
            metadata[key] = _metadata(unit=metadata.get(key, {}).get("unit"),
                                      warnings=[_warning(key, "nonfinite_derived_estimate", "The available facts and assumptions do not produce a finite estimate.")])
            return
        metadata[key] = _metadata(value, metadata.get(key, {}).get("unit"), source_type, description, period, method, warnings)

    policy_description = f"Fairworth {chosen_policy.version}: configurable illustrative modeling policy, not a company fact or an observed market estimate."
    set_value("lookback_years", 5, "benchmark_assumption", policy_description,
              "Prefer five aligned fiscal years and fall back to three when unavailable; explicit 3/5/10-year selection requires that full requested window.")
    for key in ("forecast_years", "terminal_growth"):
        set_value(key, getattr(chosen_policy, key), "benchmark_assumption", policy_description,
                  "Analyst-editable policy setting; numeric values are illustrative rather than sourced market observations.",
                  warnings=[_warning(key, "illustrative_policy_default", "Calibrate this editable policy assumption to the company's risk, currency, and long-run economics.")])
    metadata["terminal_growth"]["methodology_source"] = METHODOLOGY_SOURCES["stable_growth"]
    if chosen_policy.allow_benchmark_cost_of_equity:
        set_value("cost_of_equity", chosen_policy.cost_of_equity, "benchmark_assumption", policy_description,
                  "Illustrative required return; CAPM is not claimed because observed beta and risk-free rate are unavailable.",
                  warnings=[_warning("cost_of_equity", "benchmark_discount_rate", "This benchmark is not a company-specific cost of equity; analyst calibration is required.")])
    set_value("growth_fade_to_terminal", True, "benchmark_assumption", policy_description,
              "Linearly fade forecast growth toward terminal growth over the selected horizon; explicit annual cash-flow arrays bypass this heuristic.")

    for key, source_field in (("revenue_growth", "revenue"), ("earnings_growth", "eps"), ("cash_flow_growth", "free_cash_flow")):
        candidates = history["growth"][source_field]
        requested_lookback = (overrides or {}).get("lookback_years")
        if requested_lookback is not None and (isinstance(requested_lookback, bool) or requested_lookback not in (3, 5, 10)):
            raise ValueError("Historical lookback must be 3, 5, or 10 fiscal years.")
        choices = (int(requested_lookback),) if requested_lookback is not None else (5, 3)
        growth = next((candidates[str(years)] for years in choices if candidates[str(years)]["status"] == "available"), None)
        if growth is None:
            metadata[key]["warnings"] = [warning for window in candidates.values() for warning in window["warnings"]][:6]
            continue
        changes = growth["annual_growth"]
        if changes and max(changes) - min(changes) > chosen_policy.maximum_annual_growth_dispersion:
            metadata[key]["warnings"] = [_warning(key, "unstable_historical_forecast_basis", "Highly variable annual changes do not support an automatic forward estimate; supply an analyst forecast.")]
            continue
        value = min(chosen_policy.maximum_forecast_growth, max(chosen_policy.minimum_forecast_growth, growth["value"]))
        warnings = list(growth["warnings"])
        if value != growth["value"]:
            warnings.append(_warning(key, "historical_growth_clamped", "Historical CAGR exceeds the explicit policy forecasting bounds; the historical fact is preserved separately."))
        set_value(key, value, "historical_estimate", f"Aligned {growth['lookback_years']}-fiscal-year reported history; a forward estimate rather than a reported forecast.",
                  f"CAGR, bounded to [{chosen_policy.minimum_forecast_growth:.0%}, {chosen_policy.maximum_forecast_growth:.0%}] by disclosed policy; DCF forecasts converge toward terminal growth.",
                  {"start": growth["start_period"], "end": growth["end_period"]}, warnings)
    user_share_confirmation = (overrides or {}).get("share_basis_confirmed") is True
    if not inputs.get("basis", {}).get("share_basis_verified", False) and not user_share_confirmation:
        metadata["earnings_growth"] = _metadata(unit="fraction", warnings=[_warning("earnings_growth", "share_class_basis_unverified", "A comparable quoted-class EPS basis must be confirmed before using reported company-level EPS growth.")])
    elif user_share_confirmation and not inputs.get("basis", {}).get("share_basis_verified", False):
        metadata["earnings_growth"]["warnings"].append(_warning("earnings_growth", "user_confirmed_share_basis", "The user confirms that reported diluted EPS history applies to this quoted share class; provider verification has not been added or inferred."))

    latest = inputs.get("values", {})
    reporting_period = inputs.get("reporting_period")
    for key in ("shares", "debt", "cash", "book_equity"):
        observed = number(latest.get(key))
        if observed is not None:
            set_value(key, observed, "reported_input", "Latest validated annual financial input used as a dated modeling baseline; it is not a current market observation.",
                      "Preserve the reported amount and unit without scaling or substituting a missing zero.", reporting_period,
                      [_warning(key, "dated_financial_baseline", "Review changes since the reporting date before treating this annual baseline as a current valuation input.")])
    recent_margins = history["margins"][-3:]
    for key, field in (("operating_margin", "operating_margin"), ("net_margin", "net_margin"), ("return_on_equity", "return_on_equity")):
        series = [number(item.get(field)) for item in recent_margins]
        if len(series) >= 3 and all(value is not None for value in series):
            set_value(key, median(series), "historical_estimate", "Median of the latest three comparable annual fundamentals observations; not a forecast fact.",
                      "Median, with no unreported company-specific adjustments.", {"start": recent_margins[0]["end_date"], "end": recent_margins[-1]["end_date"]})
    if not inputs.get("basis", {}).get("income_earnings_basis_verified", False):
        metadata["return_on_equity"] = _metadata(unit="fraction", warnings=[_warning("return_on_equity", "incompatible_earnings_basis", "A common-equity earnings numerator has not been verified.")])
        metadata["net_margin"] = _metadata(unit="fraction", warnings=[_warning("net_margin", "incompatible_earnings_basis", "A common-equity earnings numerator has not been verified for equity cash-flow forecasts.")])
    revenue = number(latest.get("revenue"))
    if revenue is not None and revenue > 0:
        for key, field in (("capex_ratio", "capex"), ("da_ratio", "depreciation_and_amortization"), ("ebitda_margin", "ebitda")):
            amount = number(latest.get(field))
            if amount is not None:
                set_value(key, amount / revenue, "historical_estimate", "Latest aligned annual amount relative to reported revenue; editable forecasting estimate.", f"{field} / revenue, same fiscal period.", reporting_period)
    taxes, pretax = number(latest.get("income_tax_expense")), number(latest.get("pretax_income"))
    if taxes is not None and pretax is not None and pretax > 0 and 0 <= taxes / pretax <= 0.5:
        set_value("tax_rate", taxes / pretax, "historical_estimate", "Reported latest annual effective tax rate; not a statutory or marginal rate.", "Income tax expense / positive pretax income, compatible annual period.", reporting_period,
                  [_warning("tax_rate", "effective_tax_rate_estimate", "A historical effective rate may include one-time items; review its suitability for forecasts.")])
    dividends, income = number(latest.get("dividends_paid")), number(latest.get("net_income"))
    if inputs.get("basis", {}).get("income_earnings_basis_verified") and dividends is not None and income is not None and income > 0 and 0 <= dividends / income <= 1:
        set_value("payout_ratio", dividends / income, "historical_estimate", "Latest annual reported cash dividends divided by reported net income; scope and clean-surplus require analyst confirmation.", "Cash dividends / annual net income; repurchases excluded explicitly.", reporting_period)

    # Independently validated, cached automatic records precede user overrides.
    # An unavailable external source must not erase a supported historical input.
    for key, record in inputs.get("automatic_assumptions", {}).items():
        if not isinstance(record, dict):
            continue
        if record.get("computed_only"):
            # Cached dependent forecasts are descriptions of the snapshot, not
            # defaults to preserve after a growth/margin input is cleared.
            continue
        if key not in metadata:
            metadata[key] = {**record, "editable": False, "read_only_only": True}
            continue
        if record.get("value") is None and metadata[key].get("value") is not None:
            continue
        if record.get("fill_only") and metadata[key].get("value") is not None:
            continue
        requested = (overrides or {}).get("lookback_years")
        if requested is not None and key in {"revenue_growth", "earnings_growth", "cash_flow_growth"} and record.get("lookback_years") not in (None, requested):
            continue
        metadata[key] = {**metadata[key], **record, "editable": record.get("editable", True), "overridden": False}

    # User inputs override estimates, while preserving the suggested defaults for reset.
    defaults = {key: item["value"] for key, item in metadata.items()}
    if overrides:
        # Reset values always reference the unmodified company defaults, even
        # when an override changes a dependent historical estimate.
        defaults = generate_assumptions(inputs, policy=chosen_policy)["values"]
    for key, value in (overrides or {}).items():
        previous = metadata.get(key, _metadata(unit=BASE_UNITS.get(key, currency)))
        if value is None:
            # Explicit None clears an assumption; omitting a key resets to the default.
            accepted = None
        elif isinstance(value, bool):
            if previous.get("unit") != "boolean":
                raise ValueError(f"{key} requires a finite numeric assumption, not a boolean.")
            accepted = value
        elif isinstance(value, list):
            if key not in ("projected_fcff", "projected_fcfe", "projected_dividends", "projected_revenue") or not 1 <= len(value) <= 30 or any(number(item) is None for item in value):
                raise ValueError("Projected cash-flow assumptions require 1 to 30 finite numeric observations.")
            accepted = [number(item) for item in value]
        elif key in ("risk_free_rate", "beta", "equity_risk_premium", "cost_of_debt") and isinstance(value, dict):
            accepted = value
        else:
            accepted = number(value)
            if accepted is None:
                raise ValueError(f"{key} requires a finite numeric assumption.")
        metadata[key] = _metadata(accepted, previous.get("unit"), "user_assumption", "Explicit user input; not a provider financial fact.",
                                  "User-supplied model assumption.", "User override", previous.get("warnings"), True)
        metadata[key]["default_value"] = defaults.get(key)

    # Forecasts are produced after overrides so user growth is reflected coherently.
    def forecast(key, base_field, growth_field):
        if key in (overrides or {}):
            return
        amount, growth = number(latest.get(base_field)), number(metadata[growth_field]["value"])
        if base_field == "trailing_eps" and amount is None and user_share_confirmation:
            amount = number(inputs.get("facts", {}).get("diluted_eps", {}).get("value"))
        if amount is not None and growth is not None:
            set_value(key, amount * (1 + growth), "derived_estimate", "One-year forecast from an explicitly reported base and an identified growth assumption.",
                      f"{base_field} × (1 + {growth_field}); this is forward, not trailing.", reporting_period,
                      list(metadata[growth_field].get("warnings", [])))
    forecast("forward_eps", "trailing_eps", "earnings_growth")
    forecast("forecast_revenue", "revenue", "revenue_growth")
    if "forecast_ebitda" not in (overrides or {}):
        forecast_revenue, margin = number(metadata["forecast_revenue"]["value"]), number(metadata["ebitda_margin"]["value"])
        if forecast_revenue is not None and margin is not None:
            set_value("forecast_ebitda", forecast_revenue * margin, "derived_estimate", "One-year revenue forecast with an explicitly disclosed EBITDA-margin estimate.",
                      "Forecast revenue × EBITDA margin, preserving aligned company facts.", reporting_period)

    # Justified stable-growth multiples are only available after explicit book
    # suitability and clean-surplus confirmation, not for every operating company.
    meaningful = metadata["book_value_meaningful"]["value"] is True
    clean_surplus = metadata["clean_surplus_confirmed"]["value"] is True
    roe, ke, growth = (number(metadata[key]["value"]) for key in ("return_on_equity", "cost_of_equity", "terminal_growth"))
    if meaningful and clean_surplus and roe is not None and ke is not None and growth is not None and roe > growth and ke > growth and roe > 0:
        sustainable_payout = 1 - growth / roe
        if "target_pb" not in (overrides or {}):
            set_value("target_pb", (roe - growth) / (ke - growth), "derived_estimate", "Justified stable-growth P/B conditional on confirmed meaningful common book equity and clean surplus.",
                      "(Sustainable ROE − g) / (Ke − g).", reporting_period,
                      [_warning("target_pb", "stable_growth_multiple_assumptions", "The stable ROE, growth, and clean-surplus framework requires analyst review.")])
        if "target_pe" not in (overrides or {}):
            set_value("target_pe", sustainable_payout / (ke - growth), "derived_estimate", "Justified forward P/E using sustainable payout implied by ROE and growth, conditional on confirmed common book basis.",
                      "(1 − g / ROE) / (Ke − g); forward EPS basis.", reporting_period,
                      [_warning("target_pe", "stable_growth_multiple_assumptions", "This mature stable-growth framework is not automatically suitable for high-growth firms.")])
    if inputs.get("automatic_evidence", {}).get("historical_annual_periods"):
        from app.valuation.forecasts import derive_forward_forecasts
        effective = {key: record.get("value") for key, record in metadata.items() if not record.get("read_only_only")}
        effective.update(overrides or {})
        fresh = derive_forward_forecasts(inputs, inputs["automatic_evidence"], chosen_policy, overrides=effective)
        for key in ("forward_eps", "forecast_revenue", "forecast_ebitda", "projected_revenue"):
            if key not in (overrides or {}) and key in fresh.get("assumptions", {}):
                metadata[key] = fresh["assumptions"][key]
    for key, item in metadata.items():
        item.setdefault("default_value", defaults.get(key))
        if key in {"risk_free_rate", "beta", "equity_risk_premium", "cost_of_debt", "net_income_growth", "book_value_per_share", "forward_affo_per_share"}:
            item["editable"] = False
    resolved = {key: item["value"] for key, item in metadata.items() if not item.get("read_only_only")}
    for key in ("forward_eps", "forecast_revenue", "forecast_ebitda", "projected_revenue"):
        if key not in (overrides or {}):
            # Models derive dependent forecasts afresh, so scenario growth edits
            # cannot accidentally retain a frozen base-scenario forecast.
            resolved[key] = None
            metadata[key]["computed_only"] = True
            metadata[key]["default_value"] = None
    return complete_assumptions({"values": resolved, "metadata": metadata, "history": history,
                                "policy": asdict(chosen_policy), "methodology_sources": METHODOLOGY_SOURCES}, inputs)


def _sourced(record: dict, field: str, require_method=False) -> tuple[float, dict]:
    if not isinstance(record, dict):
        raise ValueError(f"{field} requires a sourced observation record.")
    value = number(record.get("value"))
    observed = day(record.get("observation_date"))
    if value is None or not record.get("source") or observed is None or observed > date.today():
        raise ValueError(f"{field} requires a finite value, source, and nonfuture observation date.")
    if require_method and not (record.get("estimation_method") or record.get("method")):
        raise ValueError(f"{field} requires an identified estimation method.")
    return value, record


def estimate_cost_of_equity(risk_free_rate: dict, beta: dict, equity_risk_premium: dict) -> dict:
    """CAPM from explicitly sourced inputs; does not fetch or invent observations."""
    risk_free, rf = _sourced(risk_free_rate, "risk_free_rate")
    beta_value, beta_record = _sourced(beta, "beta", require_method=True)
    premium, erp = _sourced(equity_risk_premium, "equity_risk_premium")
    if not -0.05 <= risk_free <= 0.5 or not -5 <= beta_value <= 10 or not 0 <= premium <= 0.5:
        raise ValueError("CAPM inputs are outside supported financial bounds.")
    value = risk_free + beta_value * premium
    if not 0 < value <= 1:
        raise ValueError("The supplied CAPM inputs do not imply a valid positive cost of equity.")
    return {"value": value, "unit": "fraction", "source_type": "market_derived_estimate",
            "source_description": "CAPM from explicitly sourced risk-free rate, beta, and equity-risk premium.",
            "derivation_method": "Ke = risk-free rate + beta × equity-risk premium",
            "inputs": {"risk_free_rate": rf, "beta": beta_record, "equity_risk_premium": erp},
            "warnings": ["CAPM is a model estimate; sourced observations do not eliminate model risk."]}


def estimate_wacc(cost_of_equity: float, cost_of_debt: dict, tax_rate: float, market_equity: dict, debt_value: dict, *, allow_book_debt=False) -> dict:
    """Use sourced market capitalization and debt values; book debt needs disclosure."""
    ke, tax = number(cost_of_equity), number(tax_rate)
    kd, debt_cost = _sourced(cost_of_debt, "cost_of_debt", require_method=True)
    equity, equity_record = _sourced(market_equity, "market_equity")
    debt, debt_record = _sourced(debt_value, "debt_value")
    if ke is None or tax is None or not 0 < ke <= 1 or not 0 <= kd <= 1 or not 0 <= tax < 1 or equity <= 0 or debt < 0:
        raise ValueError("WACC requires valid discount rates, tax rate, positive market equity, and nonnegative complete debt.")
    if equity_record.get("basis") != "market_value":
        raise ValueError("Book equity cannot silently replace market-value equity in WACC.")
    debt_basis = debt_record.get("basis")
    if debt_basis != "market_value" and not (allow_book_debt and debt_basis == "book_value"):
        raise ValueError("Debt must use market value, or explicitly disclosed permitted book value.")
    equity_currency, debt_currency = equity_record.get("currency"), debt_record.get("currency")
    if not equity_currency or equity_currency != debt_currency:
        raise ValueError("Capital-structure amounts require explicit compatible currencies.")
    value = equity / (debt + equity) * ke + debt / (debt + equity) * kd * (1 - tax)
    warnings = ["WACC is a financial-model estimate and depends on the supplied capital structure."]
    if debt_basis == "book_value":
        warnings.append("Complete book debt is an explicitly permitted proxy for market debt; book equity is not substituted.")
    return {"value": value, "unit": "fraction", "source_type": "market_derived_estimate",
            "source_description": "Sourced market-value capital structure with explicitly identified debt-value basis.",
            "derivation_method": "E/(D+E) × Ke + D/(D+E) × Kd × (1 − tax rate)",
            "inputs": {"cost_of_equity": ke, "cost_of_debt": debt_cost, "tax_rate": tax,
                       "market_equity": equity_record, "debt_value": debt_record}, "warnings": warnings}
