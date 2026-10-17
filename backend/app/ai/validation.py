"""Fail closed on unsupported numeric claims; qualitative support stays limited."""
import re
from decimal import Decimal, ROUND_HALF_UP, localcontext
from app.core.exceptions import ApiError
from app.ai.safety import SECRET_PATTERN, EMAIL_PATTERN, sanitize
from app.ai.classification import ALLOWED_UNCERTAINTIES, valid_classification
from app.ai.bindings import binding_kinds, finite_number as _finite_number

QUALITATIVE_WARNING = "AI interpretations are not audited research. Citation and numeric checks do not establish semantic correctness of complex qualitative claims. Verify the original sources."

_BINDING = re.compile(r"\{\{(claim|value|period|date|model):([A-Za-z0-9_-]+)\}\}", re.ASCII)
_QUANTITY = re.compile(r"[$%€£]|\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundreds?|thousands?|millions?|billions?|trillions?|dozen|half|double|doubled|triple|tripled)\b", re.I)


def _number_issue(prose):
    # Form identifiers are labels, not numerical financial assertions.
    forms = re.sub(r"\b(?:SEC(?:\s+form)?|form)\s+(10[-‐‑‒–—][KQ])\b",
                   lambda m: m.group()[:m.start(1)-m.start()] + " " * len(m[1]), prose, flags=re.I)
    match = re.search(r"\d", forms)
    if match:
        start = match.start()
        end = start + 1
        while end < len(forms) and (forms[end].isnumeric() or forms[end] in ".,/-"):
            end += 1
        return forms[start:end], start
    for index, char in enumerate(forms):
        if char.isnumeric():
            return char, index
    match = _QUANTITY.search(forms)
    return (match.group(), match.start()) if match else (None, None)


def _binding_error(rule="ineligible_binding", **details):
    return ApiError("unsupported_ai_binding", "A research value or date was not bound to a cited source.", 502,
                    {"rule": rule, **details})


def _category_matches(finding, item):
    category = item.get("category")
    allowed = {
        "reported_fact": {"reported_fact"},
        "historical_metric": {"historical_metric", "reported_fact"},
        "valuation_output": {"valuation_output", "historical_metric", "reported_fact", "policy_estimate"},
        "policy_estimate": {"policy_estimate", "valuation_output", "historical_metric", "reported_fact"},
        "user_assumption": {"user_assumption", "policy_estimate", "valuation_output", "historical_metric", "reported_fact"},
    }
    if finding.category != "interpretation" and category not in allowed.get(finding.category, {finding.category}):
        raise ApiError("conflicting_ai_category", "A numerical claim cannot relabel policy, user or model evidence as a reported fact.", 502,
            {"rule": "claim_evidence_category_mismatch", "finding_category": finding.category,
             "evidence_category": category, "evidence_id": item.get("id"), "metric": item.get("metric")})


def _numeric_display(item):
    value, unit = item.get("value"), item.get("unit")
    if not _finite_number(value):
        raise _binding_error()
    number = Decimal(str(value))
    def fixed(amount, places=2):
        # Includes every finite IEEE-754 float without Decimal's default
        # precision raising on a large, otherwise valid source value.
        with localcontext() as context:
            context.prec = 400
            return format(amount.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP), f",.{places}f")
    if unit == "fraction":
        return fixed(number * 100) + "%"
    if unit == "percent":
        return fixed(number) + "%"
    if unit == "multiple":
        return fixed(number) + "×"
    if unit in {"models", "count", "shares", "years", "fiscal years"}:
        return format(number, ",f").rstrip("0").rstrip(".") if number != number.to_integral() else format(number, ",.0f")
    if unit in {"ratio", "number"}:
        return fixed(number)
    if isinstance(unit, str) and re.fullmatch(r"[A-Z]{3}(?:/(?:shares?|year))?", unit):
        return ("$" if unit.startswith("USD") else unit[:3] + " ") + fixed(number)
    raise _binding_error()


def _resolve_binding(match, finding, registry):
    kind, key = match.groups()
    if kind == "claim":
        if not re.fullmatch(r"0|[1-9][0-9]?", key) or int(key) >= len(finding.quantitative_claims):
            raise _binding_error("unknown_claim_binding", binding_kind=kind)
        key = finding.quantitative_claims[int(key)].evidence_id
        item = registry.get(key) if key in finding.evidence_ids else None
    else:
        item = registry.get(key) if key in finding.evidence_ids else None
    if item is None:
        raise _binding_error("uncited_or_unknown_binding", binding_kind=kind, evidence_id=key)
    eligible_kind = "value" if kind == "claim" else kind
    if eligible_kind not in binding_kinds(item):
        raise _binding_error("ineligible_binding", binding_kind=eligible_kind, evidence_id=key,
                             metric=item.get("metric"), evidence_category=item.get("category"))
    if kind in {"claim", "value"}:
        _category_matches(finding, item)
        return _numeric_display(item)
    if kind == "period":
        return item["period"]
    if kind == "date":
        return item["observation_date"][:10]
    return item["value"]


def _prose_without_bindings(text, finding, registry):
    def check(match):
        _resolve_binding(match, finding, registry)
        return " " * len(match.group())
    remainder = _BINDING.sub(check, text)
    if "{" in remainder or "}" in remainder:
        offset = next(index for index, char in enumerate(remainder) if char in "{}")
        raise _binding_error("malformed_binding", rejected_span=text[offset:offset + 140])
    return remainder


def validate_findings(findings, registry):
    references = set()
    for finding in findings:
        if not valid_classification(finding.category, finding.uncertainty):
            message = ("An interpretation cannot be presented as a documented fact."
                       if finding.category == "interpretation" and finding.uncertainty == "documented"
                       else "The research category and uncertainty combination is not permitted.")
            raise ApiError("conflicting_ai_category", message, 502,
                           {"rule": "category_uncertainty_mismatch", "finding_category": finding.category,
                            "finding_uncertainty": finding.uncertainty,
                            "allowed_uncertainties": list(ALLOWED_UNCERTAINTIES.get(finding.category, ()))})
        ids = set(finding.evidence_ids)
        if not ids or ids - registry.keys():
            raise ApiError("unsupported_ai_citation", "The generated research contained unsupported source references.", 502)
        prose = finding.title + " " + finding.explanation
        for field in ("title", "explanation"):
            text = getattr(finding, field)
            try:
                if field == "title" and ("{" in text or "}" in text):
                    masked = _BINDING.sub(lambda match: " " * len(match.group()), text)
                    if "{" in masked or "}" in masked:
                        offset = next(index for index, char in enumerate(masked) if char in "{}")
                        raise _binding_error("malformed_binding", rejected_span=text[offset:offset + 140])
                    offset = next(index for index, char in enumerate(text) if char in "{}")
                    raise _binding_error("title_binding_forbidden", rejected_span=text[offset:offset + 140])
                remainder = _prose_without_bindings(text, finding, registry)
            except ApiError as error:
                if isinstance(error.details, dict):
                    error.details["field"] = field
                raise
            if _number_issue(remainder)[0] is not None:
                raise ApiError("unsupported_ai_number", "The generated research included an unvalidated numerical assertion.", 502)
        if re.search(r"https?://|www\.|<[^>]+>|\]\(", prose, re.I) or SECRET_PATTERN.search(prose) or EMAIL_PATTERN.search(prose):
            raise ApiError("unsafe_ai_output", "The generated research did not meet source and privacy checks.", 502)
        if re.search(r"\b(?:(?:recommend(?:s|ed)? (?:a |to )?|you should |stock is (?:a )?)(?:buy|sell|hold)|guaranteed|certain returns|risk.free profits?)\b", prose, re.I):
            raise ApiError("unsupported_ai_recommendation", "The generated research included an unsupported recommendation or guarantee.", 502)
        for claim in finding.quantitative_claims:
            item = registry.get(claim.evidence_id)
            value = item.get("value") if item else None
            if (claim.evidence_id not in ids or item is None or "value" not in binding_kinds(item) or not _finite_number(value) or claim.value != value
                    or claim.metric != item.get("metric") or claim.unit != item.get("unit")
                    or claim.period != item.get("period") or claim.derivation != item.get("derivation")):
                raise ApiError("unsupported_ai_claim", "A generated numerical claim did not match its source, units, period or calculation.", 502)
            _category_matches(finding, item)
        categories = {registry[key].get("category") for key in ids}
        policy_output = finding.category == "valuation_output" and "policy_estimate" in categories
        if finding.category in {"reported_fact", "historical_metric", "valuation_output", "policy_estimate", "user_assumption", "filing_excerpt", "company_profile"} and finding.category not in categories and not policy_output:
            raise ApiError("conflicting_ai_category", "The research misclassified the evidence basis.", 502)
        references.update(ids)
    return sorted(references)


def render_finding(finding, registry):
    """Only server-owned source values enter prose after the raw draft validates."""
    validate_findings([finding], registry)
    result = finding.model_dump()
    for field in ("title", "explanation"):
        result[field] = _BINDING.sub(lambda match: _resolve_binding(match, finding, registry), result[field])
    for field in ("title", "explanation"):
        for match in _BINDING.finditer(getattr(finding, field)):
            if match[1] != "value":
                continue
            item = registry[match[2]]
            if not any(claim["evidence_id"] == item["id"] for claim in result["quantitative_claims"]):
                result["quantitative_claims"].append({"evidence_id": item["id"], "metric": item["metric"], "value": item["value"],
                    "unit": item["unit"], "period": item.get("period"), "derivation": item.get("derivation")})
    # Classification is source-owned. A computed policy estimate is still a
    # valuation output, but the public response retains its more specific basis.
    if result["category"] == "valuation_output" and any(registry[claim["evidence_id"]].get("category") == "policy_estimate" for claim in result["quantitative_claims"]):
        result["category"], result["uncertainty"] = "policy_estimate", "limited"
    from app.ai.schemas import Finding
    try:
        return Finding.model_validate(result).model_dump()
    except ValueError:
        raise ApiError("ai_render_limit", "The source-backed research text exceeded the response limits.", 502) from None


def validation_diagnostic(findings, registry, private_values=()):
    """Small redacted diagnostics; no raw prompts, settings, headers or history."""
    for index, finding in enumerate(findings):
        try:
            validate_findings([finding], registry)
        except ApiError as error:
            details = {"finding_index": index, "error_code": error.code, "rule": "unbound_numeric_prose" if error.code == "unsupported_ai_number" else error.code}
            if isinstance(error.details, dict):
                details.update(error.details)
            if details["rule"] == "category_uncertainty_mismatch":
                details["field"] = "uncertainty"
                details["rejected_span"] = finding.uncertainty
            for field in ("title", "explanation"):
                if details["rule"] == "category_uncertainty_mismatch":
                    break
                text = getattr(finding, field)
                if details.get("rejected_span") and details.get("field") == field:
                    span = details["rejected_span"]
                    offset = text.find(span)
                    details["excerpt"] = text[max(0, offset-70):offset+len(span)+80]
                    break
                # IDs contain digits but are never numerical assertions. Even a
                # rejected binding must not produce a spurious '08' diagnostic.
                remainder = _BINDING.sub(lambda match: " " * len(match.group()), text)
                evidence_id = details.get("evidence_id")
                binding = next((match for match in _BINDING.finditer(text) if match[2] == evidence_id), None)
                if binding is not None:
                    details.update(field=field, rejected_span=binding.group(), excerpt=text[max(0, binding.start()-70):binding.end()+80])
                    break
                span, offset = _number_issue(remainder) if error.code == "unsupported_ai_number" else (None, None)
                if span is not None:
                    details.update(field=field, rejected_span=span, excerpt=text[max(0, offset-70):offset+130])
                    break
            evidence_ids = list(dict.fromkeys([details.get("evidence_id"), *finding.evidence_ids]))
            details["evidence"] = [{key: registry[evidence_id].get(key) for key in ("id", "category", "metric", "value", "unit", "period", "observation_date", "provider", "derivation")}
                                   for evidence_id in evidence_ids if evidence_id in registry and not isinstance(registry[evidence_id].get("value"), (dict, list))][:6]
            return sanitize(details, private_values)
    return {"status": "valid"}
