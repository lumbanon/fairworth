"""Forecast revenue × target EV/revenue, with a complete equity bridge."""

from app.valuation.models.common import enterprise_bridge, resolve_forecast_revenue
from app.valuation.validation import model, multiple, number, valued


@model
def calculate(inputs):
    revenue, basis = resolve_forecast_revenue(inputs)
    target = multiple(inputs, "target_ev_revenue")
    shares = number(inputs, "shares", positive=True)
    equity, bridge = enterprise_bridge(inputs, revenue * target)
    return valued(equity / shares, {**bridge, "forecast_revenue": revenue,
                                   "target_ev_revenue": target, "forecast_basis": basis, "shares": shares},
                  ["Revenue multiples do not independently establish profitability or sustainable margins."])
