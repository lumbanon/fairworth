"""Explicit/derived forward EPS × user-sourced target P/E."""

from app.valuation.models.common import resolve_forward_eps
from app.valuation.validation import model, multiple, valued


@model
def calculate(inputs):
    eps, basis = resolve_forward_eps(inputs)
    target = multiple(inputs, "target_pe")
    return valued(eps * target, {"forward_eps": eps, "target_pe": target, "earnings_basis": basis})
