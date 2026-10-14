"""Equity cash flows discounted at Ke; debt is never subtracted a second time."""

from app.valuation.models.common import discounted_cash_flows
from app.valuation.validation import model, number, valued


@model
def calculate(inputs):
    shares = number(inputs, "shares", positive=True)
    equity_value, details, warnings = discounted_cash_flows(inputs, "fcfe", "cost_of_equity")
    return valued(equity_value / shares, {**details, "equity_value": equity_value, "shares": shares}, warnings)
