"""Book equity plus discounted clean-surplus residual common earnings.

At n, continuing RI starts from ENDING forecast book equity, not the prior
year's capital base. Terminal ROE and book growth imply terminal retention g/ROE;
this explicit assumption is disclosed instead of incorrectly growing RI_n.
"""

from app.valuation.validation import ValuationInputError, discount, model, number, valued, years


@model
def calculate(inputs):
    book = number(inputs, "book_equity", positive=True)
    initial_book = book
    shares = number(inputs, "shares", positive=True)
    roe = number(inputs, "return_on_equity", minimum=-1, maximum=2)
    payout = number(inputs, "payout_ratio", minimum=0, maximum=1)
    rate, terminal_growth = discount(inputs, "cost_of_equity")
    count = years(inputs)
    terminal_roe = number({"terminal_roe": inputs["terminal_roe"] if inputs.get("terminal_roe") is not None else roe},
                          "terminal_roe", positive=True, maximum=2)
    retention = terminal_growth / terminal_roe
    if retention > 1:
        raise ValuationInputError("Terminal book growth exceeds sustainable retention at terminal ROE under clean surplus.")
    projection = []
    value = initial_book
    for year in range(1, count + 1):
        earnings = book * roe
        capital_charge = book * rate
        residual = earnings - capital_charge
        # The policy distributes a fraction of positive income, never negative
        # dividends. Losses instead reduce equity under the declared clean surplus.
        dividends = max(earnings, 0) * payout
        end_book = book + earnings - dividends
        if end_book <= 0:
            raise ValuationInputError("Projected common book equity becomes nonpositive; this clean-surplus model is inappropriate.")
        pv = residual / (1 + rate) ** year
        value += pv
        projection.append({"year": year, "beginning_book_equity": book, "net_income": earnings,
                           "dividends": dividends, "capital_charge": capital_charge,
                           "residual_income": residual, "present_value": pv, "ending_book_equity": end_book})
        book = end_book
    next_residual = (terminal_roe - rate) * book
    terminal_value = next_residual / (rate - terminal_growth)
    terminal_pv = terminal_value / (1 + rate) ** count
    value += terminal_pv
    warnings = ["Clean surplus assumes no unmodeled OCI, buybacks, issuance, or other book-equity adjustments.",
                "Terminal payout is inferred from sustainable book growth and terminal ROE, independently of forecast payout."]
    if retention < 0:
        warnings.append("Terminal distributions exceed earnings, implying return of capital and declining common book equity.")
    return valued(value / shares, {"initial_book_equity": initial_book, "shares": shares,
                                   "projection": projection, "terminal_roe": terminal_roe,
                                   "terminal_payout_ratio": 1 - retention, "terminal_residual_income": next_residual,
                                   "terminal_growth": terminal_growth, "terminal_value": terminal_value,
                                   "terminal_present_value": terminal_pv, "equity_value": value},
                  warnings)
