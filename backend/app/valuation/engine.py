"""Authoritative deterministic Provider valuation; fetching lives in a service."""
from copy import deepcopy
from datetime import UTC, datetime
import math

from app.core.exceptions import ApiError
from app.valuation.assumptions import generate_assumptions, estimate_cost_of_equity, estimate_wacc
from app.valuation.confidence import assess_confidence
from app.valuation.eligibility import MODEL_NAMES, eligibility
from app.valuation.models import MODEL_FUNCTIONS
from app.valuation.models.reverse_dcf import calculate as reverse_dcf
from app.valuation.scenarios import SCENARIOS, scenario_defaults, scenario_order_warnings
from app.valuation.schemas import MODEL_IDS, ValuationRequest
from app.valuation.sensitivity import calculate_sensitivity
from app.valuation.weighting import GROUPS, GROUP_BUDGETS, combine_valuations, comparisons, suggest_weights

ENGINE_VERSION = "1.0.0"


def comparison_market(inputs, manual=None):
    observed = inputs.get("market") or {}
    currency = inputs.get("currency")
    raw_price = observed.get("price")
    compatible = observed.get("currency") == currency
    price = raw_price if compatible and isinstance(raw_price, (int, float)) and not isinstance(raw_price, bool) and math.isfinite(raw_price) and raw_price > 0 else None
    result = {"price": price, "currency": currency, "source_type": "provider" if price is not None else "unavailable",
              "label": "Provider observation" if price is not None else "Market price unavailable",
              "price_timestamp": observed.get("price_timestamp"), "retrieved_at": observed.get("retrieved_at"),
              "provider": observed.get("provider"), "status": observed.get("status", "unavailable"),
              "provider_price": raw_price, "provider_currency": observed.get("currency"),
              "warnings": observed.get("warnings", [])}
    if manual is not None:
        if manual.currency != currency:
            raise ApiError("incompatible_currency", "The user-provided market price must use the valuation reporting currency.", 422)
        result.update(price=manual.value, source_type="user", label="User-provided market price", price_timestamp=None, status="user_provided")
    return result


def _discount_defaults(inputs, defaults, discount_rates, explicit=None):
    if discount_rates is None:
        return defaults
    records = discount_rates.model_dump(mode="json", exclude_none=True)
    explicit = explicit or {}
    def safe_estimate(function, *args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (ValueError, TypeError) as error:
            return {"value": None, "source_type": "unavailable", "warnings": [str(error)]}
    ke = safe_estimate(estimate_cost_of_equity, records.get("risk_free_rate"), records.get("beta"), records.get("equity_risk_premium"))
    market = inputs.get("market") or {}
    equity = records.get("equity_market_value")
    if equity is None and market.get("market_cap") and market.get("currency") == inputs.get("currency"):
        equity = {"value": market["market_cap"], "source": market.get("provider") or "market provider", "observation_date": str(market.get("price_timestamp", ""))[:10], "currency": market["currency"], "basis": "market_value"}
    debt = records.get("debt_market_value")
    if debt is None and records.get("allow_book_debt") and inputs["values"].get("debt") is not None:
        debt = {"value": inputs["values"]["debt"], "source": "Explicitly permitted reported book-debt proxy", "observation_date": (inputs.get("reporting_period") or {}).get("end_date"), "currency": inputs.get("currency"), "basis": "book_value"}
    wacc = safe_estimate(estimate_wacc, explicit.get("cost_of_equity", ke.get("value")), records.get("cost_of_debt"), records.get("tax_rate", defaults["values"].get("tax_rate")), equity, debt, allow_book_debt=records.get("allow_book_debt", False))
    for key, metadata in (("cost_of_equity", ke), ("wacc", wacc)):
        if metadata.get("value") is not None:
            defaults["values"][key] = metadata["value"]
            defaults["metadata"][key] = {**metadata, "editable": True, "overridden": False, "default_value": metadata["value"]}
        else:
            defaults["metadata"].setdefault(key, {})["warnings"] = metadata.get("warnings", [])
    return defaults


def resolve_assumptions(inputs, default, overrides, policy=None):
    """Keep default provenance while only explicit edits are marked user supplied."""
    combined = {key: value for key, value in default["values"].items()
                if (value is not None or default.get("metadata", {}).get(key, {}).get("overridden"))
                and not default.get("metadata", {}).get(key, {}).get("computed_only")}
    recompute_growth = {"revenue_growth", "earnings_growth", "cash_flow_growth"} - set(overrides) if "lookback_years" in overrides else set()
    for key in recompute_growth:
        combined.pop(key, None)
    combined.update(overrides)
    resolved = generate_assumptions(inputs, overrides=combined, policy=policy)
    for key, metadata in default["metadata"].items():
        if key not in overrides and key not in recompute_growth:
            if metadata.get("computed_only"):
                continue
            if metadata.get("source_type") == "unavailable" and resolved["values"].get(key) is not None:
                continue
            resolved["metadata"][key] = deepcopy(metadata)
            resolved["metadata"][key]["value"] = resolved["values"].get(key)
    return resolved


def calculation_values(inputs, assumptions):
    effective = {key: value for key, value in assumptions["values"].items()
                 if value is not None or assumptions.get("metadata", {}).get(key, {}).get("overridden")}
    values = {**inputs["values"], **effective, "currency": inputs.get("currency"),
              "shares_unit": "shares", "amount_scale": "units", "share_scale": "units"}
    if values.get("share_basis_confirmed"):
        for target, field in (("shares", "weighted_average_diluted_shares"), ("trailing_eps", "diluted_eps")):
            if values.get(target) is None:
                values[target] = inputs.get("facts", {}).get(field, {}).get("value")
    return values


def evaluate_model(model_id, inputs, assumptions, overridden=()):
    values = calculation_values(inputs, assumptions)
    selection = eligibility(model_id, inputs, values, overridden)
    if selection["status"] in {"ineligible", "unavailable"}:
        result = {"status": "unavailable", "fair_value": None, "warnings": [selection["reason"]], "details": {}}
    else:
        result = MODEL_FUNCTIONS[model_id](values)
        if result["status"] != "valid":
            selection = {**selection, "status": "unavailable" if result["status"] == "unavailable" else "ineligible", "reason": "; ".join(result["warnings"]), "reason_codes": ["missing_inputs" if result["status"] == "unavailable" else "invalid_model_assumptions"]}
    name, short_name = MODEL_NAMES[model_id]
    return {**result, "id": model_id, "name": name, "short_name": short_name, "eligibility": selection,
            "warnings": list(dict.fromkeys(result["warnings"] + selection["warnings"]))}


def calculate_valuation(inputs, request=None, policy=None):
    request = request or ValuationRequest()
    market = comparison_market(inputs, request.manual_market_price)
    base_default = _discount_defaults(inputs, generate_assumptions(inputs, policy=policy), request.discount_rates, request.assumptions)
    defaults = scenario_defaults(base_default)
    primary = resolve_assumptions(inputs, base_default, request.assumptions, policy)
    templates = scenario_defaults(primary)
    resolved = {}
    models = {}
    overridden = {}
    for name in SCENARIOS:
        edits = request.scenario_overrides.get(name, {})
        overridden[name] = set(request.assumptions) | set(edits)
        resolved[name] = resolve_assumptions(inputs, templates[name], edits, policy)
        models[name] = [evaluate_model(model_id, inputs, resolved[name], overridden[name]) for model_id in MODEL_IDS]
        for model in models[name]:
            model.update(comparisons(model["fair_value"], market["price"]))
    recommended, explanations = suggest_weights(models["base"])
    configured = {model_id: GROUP_BUDGETS[group] * preference / sum(members.values()) for group, members in GROUPS.items() for model_id, preference in members.items()}
    configured.update(recommended)
    configured.update(request.weights)
    enabled = list(dict.fromkeys(request.enabled_models)) if request.enabled_models is not None else [model["id"] for model in models["base"] if model["eligibility"]["status"] != "ineligible"]
    scenarios = {}
    for name in SCENARIOS:
        for model in models[name]:
            model["eligibility"]["recommended_weight"] = recommended.get(model["id"], 0)
            model["eligibility"]["weight_explanation"] = explanations.get(model["id"], "Inactive until required inputs are available; the configured preference is retained.")
        summary = combine_valuations(models[name], enabled, configured, market["price"])
        scenarios[name] = {"models": models[name], "summary": summary, "assumptions": resolved[name], "confidence": assess_confidence(inputs, models[name], summary, resolved[name])}
    reverse_inputs = calculation_values(inputs, resolved["base"])
    # The growth variable is solved, rather than required as an existing forecast.
    reverse_check = {**reverse_inputs}
    for key in ("cash_flow_growth", "revenue_growth"):
        if reverse_check.get(key) is None:
            reverse_check[key] = 0
    reverse_selection = eligibility("fcff", inputs, reverse_check, overridden["base"])
    if market["price"] is None:
        reverse = {"status": "unavailable", "implied_growth": None, "warnings": ["A valid provider or user-provided market price is required."], "details": {}}
    elif reverse_selection["status"] in {"unavailable", "ineligible"}:
        reverse = {"status": "unavailable", "implied_growth": None, "warnings": [reverse_selection["reason"]], "details": {}}
    else:
        reverse = reverse_dcf(reverse_inputs, market["price"])
    grid = None
    if request.sensitivity:
        spec = request.sensitivity
        base_model = next(model for model in models["base"] if model["id"] == spec.model_id)
        def point(model_id, edits):
            assumptions = resolve_assumptions(inputs, resolved["base"], edits, policy)
            return evaluate_model(model_id, inputs, assumptions, overridden["base"] | set(edits))
        grid = calculate_sensitivity(spec, resolved["base"], base_model, point, inputs.get("currency"))
    warnings = deepcopy(inputs.get("warnings", [])) + scenario_order_warnings(scenarios)
    warnings = list({(item.get("field"), item.get("code"), item.get("message")): item for item in warnings}.values())
    return {"engine_version": ENGINE_VERSION, "calculated_at": datetime.now(UTC).isoformat(), "company": inputs["company"], "currency": inputs.get("currency"),
            "financials": {"reporting_period": inputs.get("reporting_period"), "retrieved_at": inputs.get("financial_retrieved_at"), "source_references": inputs.get("source_references", []), "facts": inputs.get("facts", {}), "basis": inputs.get("basis", {})},
            "defaults": defaults, "scenarios": scenarios, "suggested_weights": recommended, "configured_weights": configured,
            "enabled_models": enabled, "market": market, "reverse_dcf": reverse, "sensitivity": grid, "warnings": warnings, "confidence": scenarios["base"]["confidence"]}
