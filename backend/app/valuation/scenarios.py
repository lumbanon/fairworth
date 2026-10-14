"""Scenario changes affect economic assumptions before models are recalculated."""
from copy import deepcopy

SCENARIOS = ("bear", "base", "bull")


def scenario_defaults(base):
    result = {name: deepcopy(base) for name in SCENARIOS}
    for name, direction in (("bear", -1), ("bull", 1)):
        values, metadata = result[name]["values"], result[name]["metadata"]
        changes = {}
        for key in ("revenue_growth", "earnings_growth", "cash_flow_growth"):
            if values.get(key) is not None:
                changes[key] = max(-0.95, min(2, values[key] + direction * 0.02))
        for key in ("operating_margin", "ebitda_margin", "return_on_equity", "terminal_roe"):
            if values.get(key) is not None:
                lower = -1 if key in {"operating_margin", "return_on_equity"} else 0
                upper = 2 if key in {"return_on_equity", "terminal_roe"} else 1
                changes[key] = max(lower, min(upper, values[key] + direction * 0.02))
        for key in ("wacc", "cost_of_equity"):
            if values.get(key) is not None:
                changes[key] = max(0.001, min(1, values[key] - direction * 0.01))
        if values.get("terminal_growth") is not None:
            changes["terminal_growth"] = max(-0.1, min(0.1, values["terminal_growth"] + direction * 0.005))
        for key in ("target_pe", "target_ev_ebitda", "target_ev_revenue", "target_pb", "target_p_affo", "target_peg"):
            if values.get(key) is not None:
                changes[key] = min(10 if key == "target_peg" else 200, values[key] * (1 + direction * 0.1))
        # Explicit future point estimates are scenario inputs, not immutable facts.
        for key in ("forward_eps", "forecast_revenue", "forecast_ebitda", "forecast_affo"):
            if values.get(key) is not None:
                changes[key] = values[key] * (1 + direction * 0.1)
        for key in ("capex_ratio", "nwc_ratio"):
            if values.get(key) is not None:
                lower, upper = (-1, 1) if key == "nwc_ratio" else (0, 3)
                changes[key] = max(lower, min(upper, values[key] - direction * 0.01))
        for key, value in changes.items():
            values[key] = value
            old = metadata.get(key, {})
            metadata[key] = {**old, "value": value, "source_type": "scenario_assumption", "source_description": f"{name.title()} operating assumption based on the primary default; editable and illustrative.", "derivation_method": "Shift the underlying assumption, then rerun the complete valuation model.", "overridden": False}
    return result


def scenario_order_warnings(scenarios):
    values = [scenarios[name]["summary"]["fair_value"] for name in SCENARIOS]
    if all(value is not None for value in values) and not values[0] <= values[1] <= values[2]:
        return [{"field": "scenarios", "code": "scenario_ordering", "message": "Bear/base/bull ordering differs from the usual ordering. Review signed cash flows, model exclusions and scenario assumptions."}]
    return []
