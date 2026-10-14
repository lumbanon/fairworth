"""Pure model registry and explicit alternative financial input requirements."""

from app.valuation.models import (ddm, ev_ebitda, ev_revenue, fcfe_dcf, fcff_dcf,
                                  forward_pe, graham, peg, price_to_book, reit_affo, residual_income)
from app.valuation.models.common import BRIDGE_INPUTS

MODEL_FUNCTIONS = {"fcff": fcff_dcf.calculate, "fcfe": fcfe_dcf.calculate,
                   "pe": forward_pe.calculate, "evEbitda": ev_ebitda.calculate,
                   "evRevenue": ev_revenue.calculate, "peg": peg.calculate,
                   "graham": graham.calculate, "dividend": ddm.calculate,
                   "residual": residual_income.calculate, "pb": price_to_book.calculate,
                   "affo": reit_affo.calculate}
MODEL_REGISTRY = MODEL_FUNCTIONS

# Each entry is a list of complete alternatives, not a license to substitute
# missing financial components. The engine validates suitability separately.
_FCFF_BASE = ["shares", "wacc", "terminal_growth", "forecast_years", *BRIDGE_INPUTS]
_FCFE_BASE = ["shares", "cost_of_equity", "terminal_growth", "forecast_years"]
_DRIVERS = ["revenue", "revenue_growth", "capex_ratio", "da_ratio", "nwc_ratio"]
REQUIRED_INPUTS = {
    "fcff": [_FCFF_BASE + ["projected_fcff"], _FCFF_BASE + ["fcff", "cash_flow_growth"],
             _FCFF_BASE + ["ebit", "tax_rate", "depreciation_and_amortization", "capex", "change_nwc", "cash_flow_growth"],
             _FCFF_BASE + _DRIVERS + ["operating_margin", "tax_rate"]],
    "fcfe": [_FCFE_BASE + ["projected_fcfe"], _FCFE_BASE + ["fcfe", "cash_flow_growth"],
             _FCFE_BASE + ["net_income", "depreciation_and_amortization", "capex", "change_nwc", "net_borrowing", "cash_flow_growth"],
             _FCFE_BASE + _DRIVERS + ["net_margin", "net_borrowing"]],
    "pe": [["forward_eps", "target_pe"], ["trailing_eps", "earnings_growth", "target_pe"]],
    "evEbitda": [["forecast_ebitda", "target_ev_ebitda", "shares", *BRIDGE_INPUTS],
                 ["forecast_revenue", "ebitda_margin", "target_ev_ebitda", "shares", *BRIDGE_INPUTS],
                 ["revenue", "revenue_growth", "ebitda_margin", "target_ev_ebitda", "shares", *BRIDGE_INPUTS]],
    "evRevenue": [["forecast_revenue", "target_ev_revenue", "shares", *BRIDGE_INPUTS],
                  ["revenue", "revenue_growth", "target_ev_revenue", "shares", *BRIDGE_INPUTS]],
    "peg": [["forward_eps", "earnings_growth", "target_peg"], ["trailing_eps", "earnings_growth", "target_peg"]],
    "graham": [["trailing_eps", "book_equity", "shares"]],
    "dividend": [["dividend_per_share", "dividend_growth", "cost_of_equity"],
                 ["projected_dividends", "terminal_growth", "cost_of_equity", "forecast_years"]],
    "residual": [["book_equity", "shares", "return_on_equity", "payout_ratio", "cost_of_equity", "terminal_growth", "forecast_years"]],
    "pb": [["book_equity", "shares", "target_pb"]],
    "affo": [["forecast_affo", "shares", "target_p_affo"]],
}


def missing_inputs(model_id: str, inputs: dict) -> list[str]:
    alternatives = REQUIRED_INPUTS.get(model_id)
    if alternatives is None:
        return ["unknown_model"]
    choices = [(alternative, [key for key in alternative if inputs.get(key) is None])
               for alternative in alternatives]
    # Prefer the most fully supported route when two alternatives need the
    # same number of inputs. This explains missing borrowing/NWC rather than
    # demanding an unrelated entire forecast array from a components user.
    _, missing = min(choices, key=lambda choice: (len(choice[1]), -(len(choice[0]) - len(choice[1]))))
    return missing


def required_inputs(model_id: str) -> list[list[str]]:
    return [list(option) for option in REQUIRED_INPUTS.get(model_id, [])]
