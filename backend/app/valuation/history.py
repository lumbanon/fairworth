"""Fiscal-calendar-aware historical fundamentals; historical facts are not forecasts."""

from __future__ import annotations

import math

from app.valuation.inputs import day, number

GROWTH_FIELDS = {
    "revenue": "revenue", "eps": "diluted_eps", "net_income": "net_income",
    "operating_income": "operating_income", "operating_cash_flow": "operating_cash_flow",
    "free_cash_flow": "free_cash_flow", "dividends_paid": "dividends_paid",
}


def _warning(field: str, code: str, message: str) -> dict:
    return {"field": field, "code": code, "message": message}


def _aligned(left: dict, right: dict) -> bool:
    if left.get("currency") != right.get("currency") or not left.get("currency"):
        return False
    if right.get("fiscal_year", 0) != left.get("fiscal_year", 0) + 1:
        return False
    dates = [day(period.get(key)) for period in (left, right) for key in ("start_date", "end_date")]
    if any(item is None for item in dates):
        return False
    left_start, left_end, right_start, right_end = dates
    return (335 <= (left_end - left_start).days + 1 <= 395
            and 335 <= (right_end - right_start).days + 1 <= 395
            and abs((right_start - left_end).days - 1) <= 14
            and abs((right_end - right_start).days - (left_end - left_start).days) <= 14)


def _ratio(numerator, denominator):
    top, bottom = number(numerator), number(denominator)
    if top is None or bottom is None or bottom <= 0:
        return None
    result = top / bottom
    return result if math.isfinite(result) else None


def _filing_date(period: dict) -> str:
    return max((record.get("filed", "") for fact in period.get("facts", {}).values()
                for record in fact.get("provenance", []) if record.get("filed")), default="")


def select_annual_periods(periods: list[dict]) -> tuple[list[dict], list[dict]]:
    groups = {}
    warnings = []
    for period in periods:
        if period.get("fiscal_period") != "FY" or not isinstance(period.get("fiscal_year"), int):
            continue
        groups.setdefault(period["fiscal_year"], []).append(period)
    selected = []
    for year, group in groups.items():
        identities = {(item.get("start_date"), item.get("end_date"), item.get("currency")) for item in group}
        if len(identities) != 1:
            warnings.append(_warning("financial_period", "ambiguous_fiscal_calendar", f"FY{year} has incompatible annual dates or currencies and was excluded from history."))
            continue
        if len(group) == 1:
            selected.append(group[0])
            continue
        newest = max(_filing_date(item) for item in group)
        candidates = [item for item in group if _filing_date(item) == newest]
        if any(item.get("metrics") != candidates[0].get("metrics") for item in candidates):
            warnings.append(_warning("financial_period", "ambiguous_restatement", f"FY{year} has conflicting amounts in its latest filing context and was excluded."))
            continue
        selected.append(candidates[0])
        warnings.append(_warning("financial_period", "restatement_selected", f"FY{year} uses its latest unambiguous reported filing context."))
    return sorted(selected, key=lambda item: item["fiscal_year"]), warnings


def historical_cagr(periods: list[dict], field: str, years: int) -> dict:
    """Require years+1 continuous annual observations; do not bridge missing years."""
    if isinstance(years, bool) or not isinstance(years, int) or not 1 <= years <= 30:
        raise ValueError("Historical lookback must be an integer between 1 and 30 fiscal years.")
    selected, warnings = select_annual_periods(periods)
    result = {"value": None, "unit": "fraction", "lookback_years": years,
              "start_period": None, "end_period": None, "observations": 0,
              "status": "unavailable", "warnings": warnings, "annual_growth": []}
    if len(selected) < years + 1:
        result["warnings"].append(_warning(field, "insufficient_history", f"A {years}-year CAGR requires {years + 1} valid aligned fiscal-year observations."))
        return result
    window = selected[-(years + 1):]
    result.update(start_period=window[0]["end_date"], end_period=window[-1]["end_date"], observations=len(window))
    if any(not _aligned(left, right) for left, right in zip(window, window[1:])):
        result["warnings"].append(_warning(field, "unaligned_history", "Missing fiscal years, inconsistent currency, or a changed fiscal calendar prevents a conventional aligned CAGR."))
        return result
    amounts = [number(item.get("metrics", {}).get(field)) for item in window]
    if any(item is None for item in amounts):
        result["warnings"].append(_warning(field, "missing_historical_values", "At least one observation in the aligned window is unavailable."))
        return result
    if any(item <= 0 for item in amounts):
        result["warnings"].append(_warning(field, "nonpositive_growth_basis", "Conventional CAGR is unavailable across nonpositive values or sign changes; negative financial facts are preserved."))
        return result
    if field in ("basic_eps", "diluted_eps"):
        shares = [number(item.get("metrics", {}).get("weighted_average_diluted_shares")) for item in window]
        if any(item is None or item <= 0 for item in shares):
            result["warnings"].append(_warning(field, "missing_historical_share_basis", "Historical EPS comparisons require dated diluted share denominators for each observation."))
            return result
        if any(max(previous, current) / min(previous, current) > 3 for previous, current in zip(shares, shares[1:])):
            result["warnings"].append(_warning(field, "unverified_split_basis", "A large share-count change indicates a possible split or class change; the EPS series has not been verified on a consistent adjusted basis."))
            return result
    # log ratios avoid overflow for a tiny but finite starting amount.
    try:
        value = math.expm1((math.log(amounts[-1]) - math.log(amounts[0])) / years)
    except (OverflowError, ValueError):
        value = None
    if value is None or not math.isfinite(value):
        result["warnings"].append(_warning(field, "nonfinite_historical_growth", "The available finite observations produce a nonfinite growth ratio."))
        return result
    changes = []
    for previous, current in zip(amounts, amounts[1:]):
        change = current / previous - 1
        if not math.isfinite(change):
            result["warnings"].append(_warning(field, "nonfinite_historical_growth", "An annual change is not finite."))
            return result
        changes.append(change)
    result.update(value=value, status="available", annual_growth=changes)
    if any(abs(item) > 1 for item in changes) or max(changes) - min(changes) > 1:
        result["warnings"].append(_warning(field, "extraordinary_historical_growth", "Historical changes exceed 100% or are highly variable; base effects, acquisitions, one-time events, and comparability require review."))
    return result


def analyze_history(periods: list[dict], lookbacks=(3, 5, 10)) -> dict:
    selected, warnings = select_annual_periods(periods)
    growth = {name: {str(years): historical_cagr(selected, field, years) for years in lookbacks}
              for name, field in GROWTH_FIELDS.items()}
    margins = []
    for index, period in enumerate(selected):
        values = period.get("metrics", {})
        previous = selected[index - 1] if index else None
        equity, previous_equity = number(values.get("shareholders_equity")), number(previous.get("metrics", {}).get("shareholders_equity")) if previous else None
        average_equity = (equity + previous_equity) / 2 if equity is not None and equity > 0 and previous_equity is not None and previous_equity > 0 and _aligned(previous, period) else None
        margins.append({
            "fiscal_year": period["fiscal_year"], "end_date": period["end_date"], "currency": period.get("currency"),
            "operating_margin": _ratio(values.get("operating_income"), values.get("revenue")),
            "free_cash_flow_margin": _ratio(values.get("free_cash_flow"), values.get("revenue")),
            "net_margin": _ratio(values.get("net_income"), values.get("revenue")),
            "return_on_equity": _ratio(values.get("net_income"), average_equity),
            "diluted_shares": values.get("weighted_average_diluted_shares"),
        })
    dividends = {
        "basis": "reported total annual cash dividends; per-share dividends require a verified dividend series",
        "annual_amounts": [{"fiscal_year": item["fiscal_year"], "end_date": item["end_date"],
                            "value": item.get("metrics", {}).get("dividends_paid"), "unit": item.get("currency")}
                           for item in selected],
        "stable_per_share_dividend_verified": False,
    }
    return {"growth": growth, "margins": margins, "dividends": dividends,
            "observations": len(selected), "warnings": warnings,
            "limitations": ["Historical growth is not a forward forecast.", "One-time events and economic comparability require analyst review; no automated adjustment is invented."]}
