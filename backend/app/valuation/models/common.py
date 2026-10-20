"""Shared transparent cash-flow projections and enterprise-equity bridge."""

from __future__ import annotations

from collections.abc import Mapping

from app.valuation.validation import ValuationInputError, discount, growth, number, years

BRIDGE_INPUTS = ("debt", "cash", "preferred_equity", "minority_interest", "other_nonoperating_assets")


def enterprise_bridge(inputs: Mapping, enterprise_value: float) -> tuple[float, dict]:
    bridge = {key: number(inputs, key, minimum=0) for key in BRIDGE_INPUTS}
    net_debt = bridge["debt"] - bridge["cash"]
    equity_value = (enterprise_value - net_debt - bridge["preferred_equity"]
                    - bridge["minority_interest"] + bridge["other_nonoperating_assets"])
    return equity_value, {**bridge, "net_debt": net_debt, "enterprise_value": enterprise_value,
                          "equity_value": equity_value,
                          "other_nonoperating_assets_basis": "Excludes cash already added separately; no duplicate nonoperating assets.",
                          "bridge_formula": "EV - debt + cash - preferred equity - minority interest + other nonoperating assets"}


def resolve_forward_eps(inputs: Mapping) -> tuple[float, str]:
    if inputs.get("forward_eps") is not None:
        return number(inputs, "forward_eps", positive=True), "explicit forward EPS"
    trailing = number(inputs, "trailing_eps", positive=True)
    earnings_growth = growth(inputs, "earnings_growth")
    return trailing * (1 + earnings_growth), "reported trailing EPS × (1 + assumed earnings growth)"


def resolve_forecast_revenue(inputs: Mapping) -> tuple[float, str]:
    if inputs.get("forecast_revenue") is not None:
        return number(inputs, "forecast_revenue", positive=True), "explicit forecast revenue"
    return (number(inputs, "revenue", positive=True) * (1 + growth(inputs, "revenue_growth")),
            "reported revenue × (1 + assumed revenue growth)")


def component_cash_flow(inputs: Mapping, kind: str) -> tuple[float, dict]:
    da = number(inputs, "depreciation_and_amortization", minimum=0)
    capex = number(inputs, "capex", minimum=0)
    change_nwc = number(inputs, "change_nwc")
    if kind == "fcff":
        ebit = number(inputs, "ebit")
        tax = number(inputs, "tax_rate", minimum=0, maximum=1)
        # Applying a supplied effective tax rate to losses is an explicit tax-benefit
        # assumption, not an assertion that the company can immediately monetize it.
        value = ebit * (1 - tax) + da - capex - change_nwc
        return value, {"ebit": ebit, "tax_rate": tax, "nopat": ebit * (1 - tax),
                       "depreciation_and_amortization": da, "capex": capex, "change_nwc": change_nwc}
    net_income = number(inputs, "net_income")
    net_borrowing = number(inputs, "net_borrowing")
    value = net_income + da - capex - change_nwc + net_borrowing
    return value, {"net_income": net_income, "depreciation_and_amortization": da,
                   "capex": capex, "change_nwc": change_nwc, "net_borrowing": net_borrowing}


def cash_flow_projection(inputs: Mapping, kind: str) -> tuple[list[dict], str]:
    count = years(inputs)
    fade = inputs.get("growth_fade_to_terminal", False)
    if fade is None:
        fade = False
    if not isinstance(fade, (bool, int, float)) or fade not in (False, True):
        raise ValuationInputError("growth_fade_to_terminal must be a boolean or 0/1 flag.")

    def forecast_growth(initial: float, year: int) -> float:
        if not fade or count == 1:
            return initial
        terminal = number(inputs, "terminal_growth", minimum=-0.5, maximum=0.15)
        return initial + (terminal - initial) * (year - 1) / (count - 1)

    explicit = inputs.get(f"projected_{kind}")
    if explicit is not None:
        if not isinstance(explicit, (list, tuple)) or len(explicit) != count:
            raise ValuationInputError(f"projected_{kind} must contain one cash flow for each forecast year.")
        return [{"year": index + 1, "cash_flow": number({"cash_flow": value}, "cash_flow")}
                for index, value in enumerate(explicit)], "explicit annual cash-flow forecasts"
    explicit_revenue = inputs.get("projected_revenue")
    driver_keys = ("revenue", "capex_ratio", "da_ratio", "nwc_ratio") + (() if explicit_revenue is not None else ("revenue_growth",))
    income_driver = "operating_margin" if kind == "fcff" else "net_margin"
    if inputs.get(kind) is None and all(inputs.get(key) is not None for key in (*driver_keys, income_driver)):
        revenue = number(inputs, "revenue", positive=True)
        if explicit_revenue is not None and (not isinstance(explicit_revenue, (list, tuple)) or len(explicit_revenue) != count):
            raise ValuationInputError("projected_revenue must contain one positive revenue for each forecast year.")
        rate = growth(inputs, "revenue_growth") if explicit_revenue is None else None
        margin = number(inputs, income_driver, minimum=-2, maximum=2)
        capex_ratio = number(inputs, "capex_ratio", minimum=0, maximum=3)
        da_ratio = number(inputs, "da_ratio", minimum=0, maximum=3)
        nwc_ratio = number(inputs, "nwc_ratio", minimum=-2, maximum=2)
        tax = number(inputs, "tax_rate", minimum=0, maximum=1) if kind == "fcff" else None
        net_borrowing = number(inputs, "net_borrowing") if kind == "fcfe" else None
        rows = []
        for year in range(1, count + 1):
            previous_revenue = revenue
            if explicit_revenue is not None:
                revenue = number({"revenue": explicit_revenue[year - 1]}, "revenue", positive=True)
                year_growth = revenue / previous_revenue - 1
            else:
                year_growth = forecast_growth(rate, year)
                revenue *= 1 + year_growth
            income = revenue * margin
            da, capex, change = revenue * da_ratio, revenue * capex_ratio, (revenue - previous_revenue) * nwc_ratio
            cash_flow = (income * (1 - tax) + da - capex - change if kind == "fcff"
                         else income + da - capex - change + net_borrowing)
            rows.append({"year": year, "revenue": revenue, "forecast_growth": year_growth, income_driver: margin,
                         "income": income, "depreciation_and_amortization": da,
                         "capex": capex, "change_nwc": change, "cash_flow": cash_flow,
                         **({"tax_rate": tax} if kind == "fcff" else {"net_borrowing": net_borrowing})})
        return rows, ("revenue-driven financial statement forecast; noncash NWC changes on incremental revenue; "
                      + ("explicit annual revenue path" if explicit_revenue is not None else "growth fades linearly to terminal growth" if fade else "constant explicit-period revenue growth"))
    if inputs.get(kind) is not None:
        initial, components = number(inputs, kind), {}
        basis = f"explicit or independently derived starting {kind.upper()}"
    else:
        initial, components = component_cash_flow(inputs, kind)
        basis = ("EBIT × (1 - tax rate) + D&A - capex - ΔNWC" if kind == "fcff"
                 else "net income + D&A - capex - ΔNWC + net borrowing")
    rate = growth(inputs, "cash_flow_growth")
    rows = []
    projected = initial
    for year in range(1, count + 1):
        year_growth = forecast_growth(rate, year)
        projected *= 1 + year_growth
        rows.append({"year": year, "cash_flow": projected, "forecast_growth": year_growth,
                     "starting_components": components})
    return rows, basis + ("; growth fades linearly to terminal growth" if fade else "; constant explicit-period cash-flow growth")


def discounted_cash_flows(inputs: Mapping, kind: str, discount_key: str) -> tuple[float, dict, list[str]]:
    rate, terminal_growth = discount(inputs, discount_key)
    projection, basis = cash_flow_projection(inputs, kind)
    total = 0.0
    for row in projection:
        row["present_value"] = row["cash_flow"] / (1 + rate) ** row["year"]
        total += row["present_value"]
    terminal_key = f"terminal_{kind}"
    terminal_projection = None
    if inputs.get(terminal_key) is not None:
        next_flow = number(inputs, terminal_key)
    elif "revenue" in projection[-1]:
        # Changing revenue growth changes incremental working-capital investment.
        # Growing last-year FCF would preserve its old reinvestment requirement,
        # so terminal financial statements are projected independently.
        last = projection[-1]
        revenue = last["revenue"] * (1 + terminal_growth)
        income_driver = "operating_margin" if kind == "fcff" else "net_margin"
        income = revenue * last[income_driver]
        da = revenue * number(inputs, "da_ratio", minimum=0, maximum=3)
        capex = revenue * number(inputs, "capex_ratio", minimum=0, maximum=3)
        change = (revenue - last["revenue"]) * number(inputs, "nwc_ratio", minimum=-2, maximum=2)
        next_flow = (income * (1 - last["tax_rate"]) + da - capex - change if kind == "fcff"
                     else income + da - capex - change + last["net_borrowing"])
        terminal_projection = {"year": len(projection) + 1, "revenue": revenue, "income": income,
                               "depreciation_and_amortization": da, "capex": capex,
                               "change_nwc": change, "cash_flow": next_flow,
                               **({"tax_rate": last["tax_rate"]} if kind == "fcff" else {"net_borrowing": last["net_borrowing"]})}
    else:
        next_flow = projection[-1]["cash_flow"] * (1 + terminal_growth)
    terminal_value = next_flow / (rate - terminal_growth)
    terminal_pv = terminal_value / (1 + rate) ** len(projection)
    value = total + terminal_pv
    warnings = []
    if any(row["cash_flow"] < 0 for row in projection):
        warnings.append("The explicit projection contains negative cash flows; financing requirements are not clipped.")
    if next_flow <= 0:
        warnings.append("Terminal cash flow is nonpositive; the perpetuity describes continuing cash consumption.")
    if abs(value) > 1e-12 and abs(terminal_pv / value) > 0.8:
        warnings.append("More than 80% of the magnitude of the DCF estimate comes from terminal value.")
    if kind == "fcff" and any(row.get("income", row.get("starting_components", {}).get("ebit", 0)) < 0 for row in projection):
        warnings.append("Tax benefits on operating losses require an explicit supportable tax assumption.")
    return value, {"projection": projection, "forecast_basis": basis,
                   "discount_rate": rate, "terminal_growth": terminal_growth,
                   "terminal_cash_flow": next_flow, "terminal_value": terminal_value,
                   "terminal_projection": terminal_projection,
                   "terminal_present_value": terminal_pv, "projected_present_value": total,
                   "terminal_value_contribution": terminal_pv / value if abs(value) > 1e-12 else None,
                   "discounting_convention": "annual end-of-year"}, warnings
