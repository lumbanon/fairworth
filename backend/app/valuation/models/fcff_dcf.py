"""Unlevered FCFF discounted at WACC, followed by exactly one equity bridge."""

from app.valuation.models.common import discounted_cash_flows, enterprise_bridge
from app.valuation.validation import model, number, valued


@model
def calculate(inputs):
    shares = number(inputs, "shares", positive=True)
    enterprise_value, details, warnings = discounted_cash_flows(inputs, "fcff", "wacc")
    equity_value, bridge = enterprise_bridge(inputs, enterprise_value)
    return valued(equity_value / shares, {**details, **bridge, "shares": shares}, warnings)
