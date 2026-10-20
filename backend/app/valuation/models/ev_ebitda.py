"""Forecast EBITDA × target EV/EBITDA, with a complete equity bridge."""

from app.valuation.models.common import enterprise_bridge, resolve_forecast_revenue
from app.valuation.validation import model, multiple, number, valued


@model
def calculate(inputs):
    if inputs.get("forecast_ebitda") is not None:
        ebitda = number(inputs, "forecast_ebitda", positive=True)
        basis = "explicit forecast EBITDA"
    else:
        revenue, _ = resolve_forecast_revenue(inputs)
        ebitda = revenue * number(inputs, "ebitda_margin", positive=True, maximum=2)
        basis = "forecast revenue × assumed EBITDA margin"
    target = multiple(inputs, "target_ev_ebitda")
    shares = number(inputs, "shares", positive=True)
    equity, bridge = enterprise_bridge(inputs, ebitda * target)
    return valued(equity / shares, {**bridge, "forecast_ebitda": ebitda,
                                   "target_ev_ebitda": target, "forecast_basis": basis, "shares": shares})
