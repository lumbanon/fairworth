"""Conventional PEG uses earnings growth in percentage points, not decimals."""

from app.valuation.models.common import resolve_forward_eps
from app.valuation.validation import model, multiple, number, valued


@model
def calculate(inputs):
    eps, basis = resolve_forward_eps(inputs)
    rate = number(inputs, "earnings_growth", positive=True, maximum=2)
    target = multiple(inputs, "target_peg")
    pe = target * rate * 100
    if pe > 1000:
        from app.valuation.validation import ValuationInputError
        raise ValuationInputError("Implied P/E exceeds the supported multiple range.")
    return valued(eps * pe, {"forward_eps": eps, "earnings_basis": basis,
                             "target_peg": target, "growth_percent": rate * 100,
                             "justified_pe": pe, "peg_convention": "P/E divided by earnings growth in percentage points"},
                  ["PEG is an earnings-based heuristic and overlaps with Forward P/E; high growth may be unsustainable."])
