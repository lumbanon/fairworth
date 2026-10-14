"""Bounded grids run the same primitive and eligibility checks as the engine."""
from app.core.exceptions import ApiError
from app.valuation.schemas import validate_assumptions
import numpy as np

AXES = {
    "fcff": [{"wacc", "terminal_growth"}, {"revenue_growth", "operating_margin"}],
    "fcfe": [{"cost_of_equity", "terminal_growth"}],
    "pe": [{"forward_eps", "target_pe"}],
    "evEbitda": [{"forecast_ebitda", "target_ev_ebitda"}],
    "evRevenue": [{"forecast_revenue", "target_ev_revenue"}],
    "residual": [{"return_on_equity", "cost_of_equity"}],
    "dividend": [{"dividend_growth", "cost_of_equity"}],
}


def default_axis(key, center):
    if center is None:
        return []
    if key in {"forward_eps", "forecast_revenue", "forecast_ebitda"} or key.startswith("target_"):
        return [center * float(factor) for factor in np.linspace(0.8, 1.2, 5)]
    step = 0.005 if key in {"wacc", "cost_of_equity", "terminal_growth", "dividend_growth"} else 0.01
    return [round(center + offset * step, 10) for offset in (-2, -1, 0, 1, 2)]


def calculate_sensitivity(spec, assumptions, base_model, calculate_point, currency):
    if {spec.x_parameter, spec.y_parameter} not in AXES.get(spec.model_id, []):
        raise ApiError("invalid_sensitivity", "The requested model and sensitivity axes are unsupported.", 422)
    values = {**assumptions["values"], **base_model.get("details", {})}
    x_values = spec.x_values or default_axis(spec.x_parameter, values.get(spec.x_parameter))
    y_values = spec.y_values or default_axis(spec.y_parameter, values.get(spec.y_parameter))
    rows = []
    for y_value in y_values:
        cells = []
        for x_value in x_values:
            changes = {spec.x_parameter: x_value, spec.y_parameter: y_value}
            try:
                validate_assumptions(changes)
                model = calculate_point(spec.model_id, changes)
            except ValueError as error:
                model = {"status": "invalid_input", "fair_value": None, "warnings": [str(error)]}
            cells.append({"x_value": x_value, "fair_value": model["fair_value"], "status": model["status"], "warnings": model["warnings"]})
        rows.append({"y_value": y_value, "cells": cells})
    return {"model_id": spec.model_id, "x_parameter": spec.x_parameter, "y_parameter": spec.y_parameter,
            "x_label": spec.x_parameter.replace("_", " ").title(), "y_label": spec.y_parameter.replace("_", " ").title(),
            "x_values": x_values, "y_values": y_values, "rows": rows, "unit": f"{currency}/share",
            "warnings": [] if x_values and y_values else ["Both sensitivity centers require available model assumptions or a valid explicit axis."]}
