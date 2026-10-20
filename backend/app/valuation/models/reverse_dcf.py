"""Bounded growth-implied diagnostic, never an independent valuation model.

A finite grid brackets roots before bisection, so a decreasing objective works
and sampled multiple roots/flat objectives are reported as ambiguous. A bounded
grid cannot prove absence of arbitrarily narrow or even-multiplicity roots; that
numerical limitation is returned with every result. External requests select
only named model variables, never executable functions.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping

from app.valuation.models.fcff_dcf import calculate as calculate_fcff
from app.valuation.units import compatible_currencies, validate_model_units
from app.valuation.validation import ValuationInputError, finite_tree, growth, number


def solve_bounded(function: Callable[[float], float], bounds=(-0.5, 1.0), *,
                  grid_points: int = 201, max_iterations: int = 100,
                  value_tolerance: float = 1e-8, variable_tolerance: float = 1e-10) -> dict:
    low, high = bounds
    if (isinstance(low, bool) or isinstance(high, bool) or not isinstance(low, (int, float))
            or not isinstance(high, (int, float)) or not math.isfinite(low) or not math.isfinite(high)
            or low >= high or isinstance(grid_points, bool) or not isinstance(grid_points, int)
            or isinstance(max_iterations, bool) or not isinstance(max_iterations, int)
            or not 11 <= grid_points <= 401 or not 1 <= max_iterations <= 150
            or not math.isfinite(value_tolerance) or value_tolerance <= 0
            or not math.isfinite(variable_tolerance) or variable_tolerance <= 0):
        raise ValuationInputError("Reverse solver requires finite increasing bounds and bounded grid/iteration counts.")
    samples = []
    invalid_points = 0
    for index in range(grid_points):
        x = low + (high - low) * index / (grid_points - 1)
        try:
            y = function(x)
            if not math.isfinite(y):
                raise ValueError
        except (ValueError, ArithmeticError, TypeError):
            y = None
            invalid_points += 1
        samples.append((x, y))
    valid = [(x, y) for x, y in samples if y is not None]
    metadata = {"bounds": [low, high], "grid_points": grid_points,
                "invalid_grid_points": invalid_points, "max_iterations": max_iterations,
                "converged": False, "iterations": 0,
                "root_detection_limit": "Finite bracketing grid cannot guarantee detection of narrow or non-sign-changing roots."}
    if not valid:
        return {**metadata, "status": "no_solution", "roots": [], "reason": "No valid model evaluations exist within the bounds."}
    if all(abs(y) <= value_tolerance for _, y in valid):
        return {**metadata, "status": "ambiguous", "roots": [],
                "reason": "The objective is flat at the target; growth is not uniquely identifiable."}
    roots = [x for x, y in valid if abs(y) <= value_tolerance]
    failed_brackets = False
    for (left, fl), (right, fr) in zip(samples, samples[1:]):
        if fl is None or fr is None or abs(fl) <= value_tolerance or abs(fr) <= value_tolerance or fl * fr >= 0:
            continue
        a, b = left, right
        solved = False
        for iteration in range(1, max_iterations + 1):
            middle = (a + b) / 2
            try:
                value = function(middle)
                if not math.isfinite(value):
                    break
            except (ValueError, ArithmeticError, TypeError):
                break
            if abs(value) <= value_tolerance or b - a <= variable_tolerance:
                roots.append(middle)
                metadata["iterations"] = max(metadata["iterations"], iteration)
                solved = True
                break
            if fl * value < 0:
                b = middle
            else:
                a, fl = middle, value
        if not solved:
            failed_brackets = True
    unique = []
    for root in sorted(roots):
        if not unique or abs(root - unique[-1]) > max(variable_tolerance * 10, 1e-7):
            unique.append(root)
    if len(unique) > 1:
        return {**metadata, "status": "ambiguous", "roots": unique,
                "reason": "Multiple growth assumptions match the price within the supported bounds."}
    if len(unique) == 1 and not failed_brackets:
        return {**metadata, "status": "converged", "roots": unique, "converged": True,
                "reason": "A single sampled root converged within the supplied bounds."}
    return {**metadata, "status": "no_solution", "roots": unique,
            "reason": "No unique converged solution exists within the supplied growth bounds."}


def calculate(inputs: Mapping, market_price: float | None = None,
              bounds=(-0.5, 1.0), variable: str | None = None) -> dict:
    try:
        if not isinstance(inputs, Mapping):
            raise ValuationInputError("Reverse DCF inputs must be an object.")
        validate_model_units(inputs)
        if inputs.get("market_currency") is not None:
            compatible_currencies(inputs.get("currency"), inputs["market_currency"])
        price = number({"market_price": market_price if market_price is not None else inputs.get("market_price")},
                       "market_price", positive=True)
        variable = variable or ("revenue_growth" if inputs.get("fcff") is None and all(inputs.get(key) is not None for key in
                                                       ("revenue", "operating_margin", "capex_ratio", "da_ratio", "nwc_ratio"))
                                else "cash_flow_growth")
        if variable not in {"revenue_growth", "cash_flow_growth"}:
            raise ValuationInputError("The supported solved variables are revenue_growth and cash_flow_growth.")
        if inputs.get("projected_fcff") is not None:
            raise ValuationInputError("An explicit cash-flow array is fixed; a growth-implied diagnostic needs a growth-driven forecast.")
        if not isinstance(bounds, (tuple, list)) or len(bounds) != 2:
            raise ValuationInputError("Reverse growth bounds must contain two values.")
        growth({"lower": bounds[0]}, "lower")
        growth({"upper": bounds[1]}, "upper")
        held = {key: value for key, value in inputs.items() if key not in {variable, "market_price"}}
        base = calculate_fcff({**inputs, variable: 0})
        if base["status"] != "valid":
            return {"status": base["status"], "implied_growth": None, "fair_value": None,
                    "warnings": base["warnings"], "solver": {}, "held_constants": held,
                    "solved_variable": variable}

        def objective(rate):
            result = calculate_fcff({**inputs, variable: rate})
            if result["status"] != "valid":
                raise ValueError("Invalid model inputs at this grid point.")
            return result["fair_value"] - price

        solver = solve_bounded(objective, bounds, value_tolerance=max(1.0, price) * 1e-10)
        if solver["status"] == "converged":
            implied = solver["roots"][0]
            result = calculate_fcff({**inputs, variable: implied})
            solver["price_residual"] = result["fair_value"] - price
            return finite_tree({"status": "valid", "implied_growth": implied,
                                "fair_value": result["fair_value"], "solved_variable": variable,
                                "held_constants": held, "market_price": price, "solver": solver,
                                "warnings": ["Market-implied assumptions are a diagnostic, not a guaranteed forecast.",
                                             solver["root_detection_limit"]]})
        return finite_tree({"status": "unavailable", "implied_growth": None, "fair_value": None,
                            "solved_variable": variable, "held_constants": held, "market_price": price,
                            "solver": solver, "warnings": [solver["reason"], solver["root_detection_limit"]]})
    except ValuationInputError as error:
        return {"status": "unavailable" if error.missing else "invalid_input", "implied_growth": None,
                "fair_value": None, "warnings": [str(error)], "solver": {}, "held_constants": {}}


calculate_reverse_dcf = calculate
