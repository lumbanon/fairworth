"""Historical Graham number sqrt(22.5 × positive reported EPS × BVPS)."""

from math import sqrt

from app.valuation.validation import model, number, valued


@model
def calculate(inputs):
    eps = number(inputs, "trailing_eps", positive=True)
    shares = number(inputs, "shares", positive=True)
    equity = number(inputs, "book_equity", positive=True)
    bvps = equity / shares
    return valued(sqrt(22.5 * eps * bvps), {"trailing_eps": eps, "book_value_per_share": bvps,
                                          "formula": "sqrt(22.5 × EPS × BVPS)"},
                  ["The Graham number is a historical balance-sheet heuristic, not a modern universal target price."])
