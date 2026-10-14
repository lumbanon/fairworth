"""Finite, bounded model inputs; missing data is different from invalid data."""

from __future__ import annotations

import math
from collections.abc import Mapping
from decimal import Decimal
from functools import wraps
from typing import Any, Callable


class ValuationInputError(ValueError):
    def __init__(self, message: str, *, missing: bool = False, fields: list[str] | None = None):
        super().__init__(message)
        self.missing = missing
        self.fields = fields or []


def number(inputs: Mapping, key: str, *, minimum: float | None = None,
           maximum: float | None = None, positive: bool = False) -> float:
    value = inputs.get(key)
    if value is None:
        raise ValuationInputError(f"Required input '{key}' is unavailable; it is not assumed to be zero.",
                                  missing=True, fields=[key])
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValuationInputError(f"{key} must be a finite number.", fields=[key])
    try:
        result = float(value)
    except (ValueError, OverflowError):
        raise ValuationInputError(f"{key} must be finite.", fields=[key]) from None
    if not math.isfinite(result) or abs(result) > 1e24:
        raise ValuationInputError(f"{key} must be finite and within the supported magnitude.", fields=[key])
    if positive and result <= 0:
        raise ValuationInputError(f"{key} must be positive.", fields=[key])
    if minimum is not None and result < minimum or maximum is not None and result > maximum:
        raise ValuationInputError(f"{key} is outside the supported range.", fields=[key])
    return result


def growth(inputs: Mapping, key: str) -> float:
    return number(inputs, key, minimum=-0.99, maximum=2.0)


def discount(inputs: Mapping, key: str, terminal_key: str = "terminal_growth") -> tuple[float, float]:
    rate = number(inputs, key, positive=True, maximum=1)
    terminal = number(inputs, terminal_key, minimum=-0.5, maximum=0.15)
    if rate <= terminal:
        raise ValuationInputError(f"{key} must exceed {terminal_key}.", fields=[key, terminal_key])
    return rate, terminal


def years(inputs: Mapping) -> int:
    value = number(inputs, "forecast_years", minimum=1, maximum=30)
    if not value.is_integer():
        raise ValuationInputError("forecast_years must be a whole number from 1 through 30.")
    return int(value)


def multiple(inputs: Mapping, key: str) -> float:
    return number(inputs, key, positive=True, maximum=1000)


def model(function: Callable) -> Callable:
    """Public primitives never leak invalid floating point values into JSON."""
    @wraps(function)
    def wrapped(inputs: Mapping) -> dict:
        try:
            if not isinstance(inputs, Mapping):
                raise ValuationInputError("Model inputs must be an object.")
            # The engine supplies canonical absolute units. Explicit incompatible
            # metadata is rejected rather than relying on coincidentally equal scales.
            from app.valuation.units import validate_model_units
            validate_model_units(inputs)
            return function(inputs)
        except ValuationInputError as error:
            return {"status": "unavailable" if error.missing else "invalid_input",
                    "fair_value": None, "warnings": [str(error)],
                    "details": {"missing_inputs": error.fields if error.missing else [],
                                "invalid_inputs": [] if error.missing else error.fields}}
        except (OverflowError, ZeroDivisionError, FloatingPointError):
            return {"status": "invalid_input", "fair_value": None,
                    "warnings": ["The calculation exceeds supported numerical bounds."], "details": {}}
    return wrapped


def finite_tree(value: Any) -> Any:
    if isinstance(value, (float, Decimal)):
        value = float(value)
        if not math.isfinite(value):
            raise ValuationInputError("The calculation did not produce finite values.")
    elif isinstance(value, dict):
        value = {key: finite_tree(item) for key, item in value.items()}
    elif isinstance(value, (list, tuple)):
        value = [finite_tree(item) for item in value]
    return value


def valued(fair_value: float, details: dict | None = None, warnings: list[str] | None = None) -> dict:
    notices = list(warnings or [])
    if fair_value <= 0:
        notices.append("The equity estimate is nonpositive; it is preserved without clipping and requires economic interpretation.")
    return finite_tree({"status": "valid", "fair_value": fair_value,
                        "warnings": notices, "details": details or {}})
