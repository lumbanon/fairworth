"""Supported REIT forecast AFFO × P/AFFO; no GAAP-income or FCF proxies."""

from app.valuation.validation import model, multiple, number, valued


@model
def calculate(inputs):
    target = multiple(inputs, "target_p_affo")
    shares = number(inputs, "shares", positive=True)
    affo = number(inputs, "forecast_affo", positive=True)
    return valued(affo / shares * target, {"forecast_affo": affo, "forecast_affo_per_share": affo / shares,
                                           "target_p_affo": target, "shares": shares},
                  ["AFFO is issuer-defined and requires verified reconciliation; GAAP income and ordinary FCF are not substituted."])
