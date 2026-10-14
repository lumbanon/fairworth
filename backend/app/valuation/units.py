"""Explicit Decimal conversion at the canonical valuation input boundary.

Models use absolute reporting-currency amounts and actual share counts, never
statement presentation millions. Per-share reported earnings remain per-share.
No implicit foreign-exchange conversion is permitted.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation

from app.valuation.validation import ValuationInputError

SCALES = {"units": Decimal(1), "thousands": Decimal(1000),
          "millions": Decimal(1000000), "billions": Decimal(1000000000)}


def decimal_number(value: object) -> Decimal:
    if isinstance(value, bool) or value is None or not isinstance(value, (int, float, Decimal)):
        raise ValuationInputError("A financial amount must be a finite numeric value.", missing=value is None)
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise ValuationInputError("A financial amount must be finite.") from None
    if not result.is_finite():
        raise ValuationInputError("A financial amount must be finite.")
    return result


def validate_currency(currency: object) -> str:
    if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
        raise ValuationInputError("A declared three-letter reporting currency is required.", missing=currency is None)
    return currency


def compatible_currencies(first: str, second: str) -> None:
    if validate_currency(first) != validate_currency(second):
        raise ValuationInputError("Incompatible currencies require an explicit verified exchange conversion.")


def normalize_amount(value: object, currency: str, scale: str = "units") -> Decimal:
    validate_currency(currency)
    if scale not in SCALES:
        raise ValuationInputError("Unsupported monetary scale; use units, thousands, millions, or billions.")
    return decimal_number(value) * SCALES[scale]


def normalize_shares(value: object, scale: str = "units") -> Decimal:
    if scale not in SCALES:
        raise ValuationInputError("Unsupported share-count scale.")
    shares = decimal_number(value) * SCALES[scale]
    if shares <= 0:
        raise ValuationInputError("The share denominator must be positive.")
    return shares


def per_share(amount: object, shares: object, *, amount_currency: str,
              result_currency: str, amount_scale: str = "units", share_scale: str = "units") -> Decimal:
    compatible_currencies(amount_currency, result_currency)
    return normalize_amount(amount, amount_currency, amount_scale) / normalize_shares(shares, share_scale)


def validate_model_units(inputs: Mapping) -> None:
    currency = inputs.get("currency")
    if currency is not None:
        validate_currency(currency)
    for key in ("amount_currency", "forecast_currency", "book_currency"):
        if inputs.get(key) is not None:
            compatible_currencies(currency, inputs[key])
    if inputs.get("amount_unit") is not None and inputs["amount_unit"] != currency:
        raise ValuationInputError("Model amounts must be absolute reporting-currency units.")
    if inputs.get("shares_unit") is not None and inputs["shares_unit"] != "shares":
        raise ValuationInputError("Model share counts must be actual shares; convert presentation scales first.")
    for key in ("amount_scale", "share_scale"):
        if inputs.get(key) is not None and inputs[key] != "units":
            raise ValuationInputError("Model amounts and shares must use canonical units; normalize scales before calculation.")
