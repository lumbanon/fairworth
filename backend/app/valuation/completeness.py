"""An inventory of existing evidence, never a source of new financial inputs.

Groups overlap deliberately: a usable derived or policy input is also available.
No completeness percentage or statistical confidence is inferred from counts.
"""
from copy import deepcopy
from datetime import date, datetime
import re

from app.valuation.provenance import POLICY_TYPES, USER_TYPES

COMPLETENESS_VERSION = "financial-completeness-1"
GROUPS = ("available", "missing", "stale", "incompatible", "restricted", "derived", "policy", "user")
LABELS = {"debt": "Complete conventional financial debt", "total_debt": "Complete conventional financial debt",
          "ebitda": "EBITDA operating-income proxy", "ebitda_margin": "EBITDA margin",
          "shares": "Valuation share denominator", "market_price": "Comparison market price"}
_INCOMPATIBLE = re.compile(r"incompatible|conflict|mismatch|ambiguous|scope.unverified|unverified.scope", re.I)
_RESTRICTED = {"provider_subscription_required", "provider_not_authorized", "provider_authentication_failed",
               "provider_access_denied", "restricted"}


def _json(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json(item) for item in value]
    return deepcopy(value)


def _warnings(*groups):
    return list(dict.fromkeys(str(item.get("message", "")) if isinstance(item, dict) else str(item)
                              for group in groups if isinstance(group, (tuple, list)) for item in group))


def build_data_completeness(inputs, assumptions, models, market):
    """Expose exact facts/effective assumptions and their actual source status."""
    fields, groups = {}, {group: [] for group in GROUPS}
    facts, metadata = inputs.get("facts", {}), assumptions.get("metadata", {})
    period = inputs.get("reporting_period")
    as_of = inputs.get("financial_retrieved_at")

    def add(key, record, original=None):
        original = original or {}
        provenance = _json(record.get("provenance") or original.get("provenance") or [])
        provenance = provenance if isinstance(provenance, list) else []
        identifiers = [item for item in (record.get("source_identifiers") or []) if isinstance(item, str)]
        identifiers.extend(item["accn"] for item in provenance if isinstance(item, dict) and item.get("accn"))
        source = record.get("source_type") or "unavailable"
        kind = record.get("evidence_type")
        warnings = _warnings(original.get("warnings"), record.get("warnings"))
        financial_period = record.get("financial_period", record.get("period", record.get("observation_period")))
        derivation = record.get("derivation_formula") or record.get("derivation_method")
        if not derivation:
            derivation = "; ".join(dict.fromkeys(item["derivation"] for item in provenance
                                                if isinstance(item, dict) and item.get("derivation"))) or None
        provider = record.get("source_provider") or record.get("provider")
        if not provider and provenance:
            provider = "sec-edgar" if any(item.get("source") == "sec" for item in provenance if isinstance(item, dict)) else None
        observed = record.get("observation_date")
        if observed is None and isinstance(financial_period, dict):
            observed = financial_period.get("end_date", financial_period.get("end"))
        item = {"label": LABELS.get(key, key.replace("_", " ").capitalize()), "value": _json(record.get("value")),
                "unit": record.get("unit", original.get("unit")), "source_type": source, "provider": provider,
                "observation_date": _json(observed), "period": _json(financial_period),
                "retrieved_at": _json(record.get("retrieved_at", original.get("retrieved_at"))),
                "derivation": derivation, "source_identifiers": sorted(set(str(identifier) for identifier in identifiers)),
                "provenance": provenance, "warnings": warnings,
                "source_description": record.get("source_description"), "input_status": record.get("input_status", record.get("state")),
                "source_category": record.get("source_category"), "overridden": bool(record.get("overridden")),
                "dependency_fields": deepcopy(record.get("dependency_fields", []))}
        original_value = original.get("reported_value", original.get("value"))
        if original_value is not None and original_value != item["value"]:
            item["reported_value"] = _json(original_value)
        fields[key] = item
        groups["available" if item["value"] is not None else "missing"].append(key)
        if source in USER_TYPES or kind == "user" or item["overridden"]:
            groups["user"].append(key)  # Explicit null overrides remain visible.
        if item["value"] is not None and (source in POLICY_TYPES or kind == "policy" or record.get("policy_dependencies")):
            groups["policy"].append(key)
        if item["value"] is not None and (source.startswith("derived") or kind == "estimate"):
            groups["derived"].append(key)
        signals = " ".join([str(record.get("input_status", "")), str(record.get("state", "")), *warnings])
        if _INCOMPATIBLE.search(signals) or record.get("compatible") is False or record.get("scope_verified") is False:
            groups["incompatible"].append(key)
        if record.get("status") == "stale" or record.get("input_status") == "stale" or re.search(r"\bstale\b", signals, re.I):
            groups["stale"].append(key)
        elif inputs.get("data_status") == "stale" and provenance and key not in groups["user"]:
            groups["stale"].append(key)
        if any(isinstance(status, str) and status in _RESTRICTED for status in (record.get("status"), record.get("input_status"))):
            groups["restricted"].append(key)

    # The effective assumption takes precedence in this inventory; the original
    # reported fact remains inspectable and is never overwritten in inputs.
    for key in sorted(set(facts) | set(metadata)):
        add(key, metadata.get(key, facts.get(key, {})), facts.get(key))

    manual_price = market.get("source_type") == "user"
    quote = {"value": market.get("price"), "unit": f"{inputs.get('currency')}/share" if inputs.get("currency") else None,
             "source_type": "user" if manual_price else "market_observation" if market.get("price") is not None else "unavailable",
             "provider": "User" if manual_price else market.get("provider"),
             "observation_date": None if manual_price else market.get("price_timestamp"),
             "retrieved_at": None if manual_price else market.get("retrieved_at"), "period": None,
             "status": market.get("status"), "warnings": market.get("warnings", [])}
    add("market_price", quote)
    if manual_price:
        fields["market_price"]["source_description"] = "User-provided comparison price; not an official provider quote."
        fields["market_price"]["original_provider_observation"] = _json({
            "value": market.get("provider_price"), "currency": market.get("provider_currency"),
            "provider": market.get("provider"), "observation_date": market.get("provider_price_timestamp"),
            "retrieved_at": market.get("retrieved_at")})
    evidence = inputs.get("automatic_evidence", {})
    for provider_field, status in evidence.get("provider_status", {}).items():
        code = status.get("status") if isinstance(status, dict) else status
        if isinstance(code, str) and code in _RESTRICTED:
            key = f"provider_{provider_field}"
            add(key, {"value": None, "unit": "provider capability", "source_type": "unavailable",
                      "input_status": code, "source_description": "This optional source is restricted by the configured provider permissions.",
                      "warnings": [f"{provider_field}: {code}; missing fields are not replaced with estimates."]})

    # Show model blockers without assigning fabricated values to missing keys.
    for model in models:
        for key in model.get("eligibility", {}).get("missing_inputs", []):
            if key not in fields:
                add(key, {"value": None, "source_type": "unavailable",
                          "warnings": ["A required model input has no supported effective value."]})
    return {"methodology_version": COMPLETENESS_VERSION, "normalization_version": inputs.get("normalization_version"),
            "reporting_period": _json(period), "as_of": _json(as_of),
            "quote_observation_date": None if manual_price else market.get("price_timestamp"), "groups": groups, "fields": fields,
            "limitations": ["Groups can overlap; counts are not a completeness score or a probability of valuation accuracy.",
                            "Source observation, filing, retrieval and calculation dates have different meanings."]}
