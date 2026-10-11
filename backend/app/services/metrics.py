"""Financial ratios from matching normalized periods, never valuation assumptions."""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _ratio(numerator: Any, denominator: Any) -> float | None:
    top, bottom = _number(numerator), _number(denominator)
    if top is None or bottom is None or bottom <= 0:
        return None
    result = top / bottom
    return result if math.isfinite(result) else None


def _aligned_previous(period: dict, candidates: list[dict]) -> dict | None:
    """Annual growth is year over year; quarterly growth uses the same fiscal quarter."""
    matches = [
        other for other in candidates
        if other.get("fiscal_year") == period.get("fiscal_year", 0) - 1
        and other.get("fiscal_period") == period.get("fiscal_period")
        and other.get("currency", "USD") == period.get("currency", "USD")
    ]
    if len(matches) != 1:
        return None
    other = matches[0]
    try:
        length = (date.fromisoformat(period["end_date"]) - date.fromisoformat(period["start_date"])).days
        other_length = (date.fromisoformat(other["end_date"]) - date.fromisoformat(other["start_date"])).days
        end_gap = (date.fromisoformat(period["end_date"]) - date.fromisoformat(other["end_date"])).days
    except (ValueError, KeyError, TypeError):
        return None
    if abs(length - other_length) > 14 or not 335 <= end_gap <= 395:
        return None
    return other


def calculate_metrics(periods: list[dict]) -> dict:
    """Return decimal ratios with their reporting periods and structured warnings.

    ROE uses annual earnings / average beginning and ending equity. No quarterly
    annualization or zero/missing-value substitutions are made. Negative earnings
    and cash flow remain legitimate; growth across a nonpositive base is omitted.
    """
    result = []
    warnings = []
    for period in periods:
        values = period.get("metrics", {})
        previous = _aligned_previous(period, periods)
        previous_values = previous.get("metrics", {}) if previous is not None else {}
        currency = period.get("currency", "USD")
        ratios = {
            "revenue_growth": None,
            "gross_margin": None,
            "operating_margin": None,
            "net_profit_margin": None,
            "free_cash_flow_margin": None,
            "return_on_equity": None,
            "debt_to_equity": None,
            "net_debt": None,
            "historical_eps_growth": None,
            "historical_free_cash_flow_growth": None,
        }

        def warn(field: str, code: str, message: str) -> None:
            warning = {"field": field, "code": code, "message": f"FY{period.get('fiscal_year')} {period.get('fiscal_period')}: {message}"}
            if warning not in warnings:
                warnings.append(warning)

        if currency != "USD":
            warn("currency", "incompatible_currency", "ratios are unavailable for incompatible reporting units.")
        else:
            for target, numerator in (
                ("gross_margin", "gross_profit"), ("operating_margin", "operating_income"),
                ("net_profit_margin", "net_income"), ("free_cash_flow_margin", "free_cash_flow"),
            ):
                ratios[target] = _ratio(values.get(numerator), values.get("revenue"))
                if ratios[target] is None:
                    warn(target, "unavailable_ratio", "the numerator or positive revenue denominator is unavailable.")
            ratios["debt_to_equity"] = _ratio(values.get("total_debt"), values.get("shareholders_equity"))
            if ratios["debt_to_equity"] is None:
                warn("debt_to_equity", "unavailable_ratio", "complete debt or positive shareholder equity is unavailable.")
            debt, cash = _number(values.get("total_debt")), _number(values.get("cash_and_cash_equivalents"))
            if debt is not None and cash is not None:
                ratios["net_debt"] = debt - cash
            else:
                warn("net_debt", "unavailable_ratio", "complete debt and cash at the same balance-sheet date are required.")
            for target, field in (("revenue_growth", "revenue"), ("historical_eps_growth", "diluted_eps"), ("historical_free_cash_flow_growth", "free_cash_flow")):
                ratio = _ratio(values.get(field), previous_values.get(field))
                if ratio is not None:
                    ratios[target] = ratio - 1
                    if abs(ratios[target]) > 3:
                        warn(target, "suspicious_large_change", "a year-over-year change exceeds 300%; review the source filings and comparability.")
                else:
                    warn(target, "unavailable_comparable_period", "a comparable fiscal period with a positive prior value is required.")
            equity, prior_equity = _number(values.get("shareholders_equity")), _number(previous_values.get("shareholders_equity"))
            adjacent_equity_dates = False
            if previous is not None:
                try:
                    adjacent_equity_dates = date.fromisoformat(previous["end_date"]) + timedelta(days=1) == date.fromisoformat(period["start_date"])
                except (ValueError, KeyError, TypeError):
                    pass
            if period.get("fiscal_period") == "FY" and equity is not None and prior_equity is not None and adjacent_equity_dates:
                ratios["return_on_equity"] = _ratio(values.get("net_income"), (equity + prior_equity) / 2)
            if ratios["return_on_equity"] is None:
                warn("return_on_equity", "unavailable_average_equity", "annual income and compatible beginning/ending equity are required; quarterly income is not silently annualized.")
        result.append({
            "fiscal_year": period.get("fiscal_year"), "fiscal_period": period.get("fiscal_period"),
            "start_date": period.get("start_date"), "end_date": period.get("end_date"),
            "currency": currency, "metrics": ratios,
        })
    return {"periods": result, "warnings": warnings}
