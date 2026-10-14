"""Stable or explicitly multi-stage dividend discount valuation per share."""

from app.valuation.validation import ValuationInputError, discount, model, number, valued, years


@model
def calculate(inputs):
    explicit = inputs.get("projected_dividends")
    if explicit is None:
        rate, terminal_growth = discount(inputs, "cost_of_equity", "dividend_growth")
        current = number(inputs, "dividend_per_share", positive=True)
        next_dividend = current * (1 + terminal_growth)
        return valued(next_dividend / (rate - terminal_growth),
                      {"dividend_per_share": current, "next_dividend": next_dividend,
                       "cost_of_equity": rate, "dividend_growth": terminal_growth, "dividend_basis": "per share"})
    count = years(inputs)
    if not isinstance(explicit, (list, tuple)) or len(explicit) != count:
        raise ValuationInputError("projected_dividends must contain one per-share dividend for every forecast year.")
    rate, terminal_growth = discount(inputs, "cost_of_equity")
    projection = []
    for year, value in enumerate(explicit, 1):
        dividend = number({"dividend": value}, "dividend", minimum=0)
        projection.append({"year": year, "dividend": dividend, "present_value": dividend / (1 + rate) ** year})
    next_dividend = projection[-1]["dividend"] * (1 + terminal_growth)
    terminal_value = next_dividend / (rate - terminal_growth)
    terminal_pv = terminal_value / (1 + rate) ** count
    return valued(sum(row["present_value"] for row in projection) + terminal_pv,
                  {"projection": projection, "terminal_value": terminal_value,
                   "terminal_present_value": terminal_pv, "terminal_growth": terminal_growth,
                   "cost_of_equity": rate, "dividend_basis": "explicit per-share forecast"})
