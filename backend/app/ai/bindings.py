"""Source-owned binding eligibility and a request-scoped generation contract.

The model selects typed references, never formats financial values or writes
binding tokens. Public responses retain the existing flat Finding contract.
"""
from datetime import date, datetime
from functools import reduce
import math
import operator
import re
from typing import Literal

from pydantic import Field, create_model
from typing_extensions import TypeAliasType


NUMERIC_CATEGORIES = frozenset({"reported_fact", "historical_metric", "valuation_output", "policy_estimate", "user_assumption"})
COUNT_UNITS = frozenset({"models", "count", "shares", "years", "fiscal years"})
NUMBER_UNITS = COUNT_UNITS | {"fraction", "percent", "multiple", "ratio", "number"}
_PERIOD = re.compile(r"(?:10-[KQ]|FY\s*\d{4}(?:\s*(?:FY|Q[1-4]))?(?:;\s*(?:\d{4}-\d{2}-\d{2}|unknown start)\s+to\s+\d{4}-\d{2}-\d{2})?|FY\s+\d{4}(?:[,\s\u2013-]+\d{4})*|\d{4}-\d{2}-\d{2}(?:\s+to\s+\d{4}-\d{2}-\d{2})?)", re.I | re.ASCII)
_UNUSABLE = {"unavailable", "unknown", "invalid_input", "incompatible", "ineligible"}


def finite_number(value):
    try:
        return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
    except OverflowError:
        return False


def numeric_unit(unit):
    return isinstance(unit, str) and (unit in NUMBER_UNITS or bool(re.fullmatch(r"[A-Z]{3}(?:/(?:shares?|year))?", unit, re.ASCII)))


def valid_period(period):
    if not isinstance(period, str) or not _PERIOD.fullmatch(period):
        return False
    try:
        days = [date.fromisoformat(day) for day in re.findall(r"\d{4}-\d{2}-\d{2}", period, re.ASCII)]
        return len(days) < 2 or days[0] <= days[-1]
    except ValueError:
        return False


def valid_observation(observed):
    if not isinstance(observed, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)?", observed, re.ASCII):
        return False
    try:
        date.fromisoformat(observed) if len(observed) == 10 else datetime.fromisoformat(observed.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _compatible(item):
    # Missing *other* inputs, stale quotes, and policy/single-model warnings do
    # not invalidate an otherwise supported dated scalar. Source gates remain
    # authoritative; explicit incompatibility can never be restored by chat.
    return (item.get("category") != "unavailable" and item.get("compatible") is not False
            and item.get("scope_verified") is not False
            and not any(item.get(key) in _UNUSABLE for key in ("status", "input_status", "source_type", "evidence_type")
                        if isinstance(item.get(key), str)))


def binding_kinds(item):
    kinds = []
    compatible = _compatible(item)
    if compatible and item.get("category") in NUMERIC_CATEGORIES and finite_number(item.get("value")) and numeric_unit(item.get("unit")):
        kinds.append("value")
    metric, name = item.get("metric", ""), item.get("value")
    model = (compatible and item.get("provider") == "Fairworth Python valuation engine"
            and item.get("category") in {"valuation_output", "policy_estimate", "user_assumption"}
            and isinstance(metric, str) and (metric.endswith("_model_name") or metric == "valuation_method_name")
            and item.get("unit") == "text" and isinstance(name, str)
            and bool(re.fullmatch(r"[A-Za-z0-9/()& ._-]{1,100}", name, re.ASCII)))
    # Do not expose inherited reporting periods on arbitrary profile/narrative
    # text or structured aggregates as though they dated those contents.
    metadata = compatible and ("value" in kinds or model or item.get("category") == "filing_excerpt")
    if metadata and valid_observation(item.get("observation_date")):
        kinds.append("date")
    if metadata and valid_period(item.get("period")):
        kinds.append("period")
    if model:
        kinds.append("model")
    return tuple(kinds)


def binding_catalog(registry):
    result = {kind: [] for kind in ("value", "date", "period", "model", "citation_only")}
    for key, item in registry.items():
        kinds = binding_kinds(item)
        for kind in kinds or ("citation_only",):
            result[kind].append(key)
    return result


def _join_segments(segments):
    """Add only missing boundary spaces; keep source tokens and wording intact.

    References are atomic words, irrespective of the digits in their IDs. Never
    run punctuation/number substitutions over tokens or the model's free text.
    Adjacent text fragments may deliberately split a word, so only sentence
    punctuation triggers separation between two text segments.
    """
    result, previous_kind = "", "text"
    for kind, text in segments:
        if result and text:
            left = "a" if previous_kind != "text" else result[-1]
            right = "a" if kind != "text" else text[0]
            has_space = result[-1].isspace() or text[0].isspace()
            sentence = left in ".,!?;:" and (right.isalnum() or right in "$€£(“‘")
            word_boundary = (previous_kind != "text" or kind != "text") and (
                (left.isalnum() or left in ")]%”’") and (right.isalnum() or right in "$€£(“‘"))
            if not has_space and (sentence or word_boundary):
                result += " "
        result += text
        previous_kind = kind
    return result


def generation_model(schema, payload):
    """Only supported nested anyOf, refs and finite enums; no conditionals.

    Each ID enum is emitted once in $defs, shared by every classification
    branch. At most 180 context records keep the total below 1,000 enum values.
    Empty binding groups are omitted rather than emitting invalid empty enums.
    """
    from app.ai.schemas import Finding, QuantitativeClaim, Strict, ReportSections

    package = payload.get("evidence", payload)
    registry = package.get("registry", {})
    if len(registry) > 181 or any(not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", key, re.ASCII) for key in registry):
        from app.core.exceptions import ApiError
        raise ApiError("ai_context_too_large", "The research evidence exceeds the supported schema limits.", 422)
    catalog = binding_catalog(registry)
    text_part = create_model("ResearchText", __base__=Strict,
        kind=(Literal["text"], ...),
        text=(str, Field(min_length=1, max_length=800, pattern=r"^[^{}]*$",
                         description="Plain qualitative prose only. No quantities, dates, binding tokens or evidence IDs.")))
    parts = [text_part]
    for kind in ("value", "date", "period", "model"):
        if catalog[kind]:
            parts.append(create_model("Research" + kind.capitalize(), __base__=Strict,
                kind=(Literal[kind], ...), evidence_id=(Literal[tuple(catalog[kind])], ...)))
    # A single model works for an empty registry too (e.g. parser error tests).
    part_type = reduce(operator.or_, parts)
    citations = TypeAliasType("ResearchEvidenceId", Literal[tuple(registry)]) if registry else str
    finding = create_model("BoundFinding", __base__=Finding,
        title=(str, Field(min_length=1, max_length=160, pattern=r"^[^{}0-9]*$",
                          description="Short qualitative title. No bindings, amounts, dates or counts, including spelled-out counts.")),
        explanation=(list[part_type], Field(min_length=1, max_length=32,
            description="Ordered text and typed source references. Every eligible typed reference is automatically cited by the server in this finding. evidence_ids selects optional additional qualitative sources; it need not repeat typed IDs. The server inserts exact source values. Never write raw binding tokens.")),
        evidence_ids=(list[citations], Field(min_length=0, max_length=12 if registry else 0,
            description="Optional additional qualitative citations. Typed references supply their own source IDs; the server derives complete per-finding coverage.")),
        quantitative_claims=(list[QuantitativeClaim], Field(max_length=0, description="Always empty. The server owns exact financial claims.")))
    if schema.__name__ == "ChatDraft":
        return create_model(schema.__name__, __base__=Strict,
                            answer=(list[finding], Field(min_length=1, max_length=6)))
    if schema.__name__ != "ReportDraft":
        raise ValueError("Unknown research draft contract.")
    sections = create_model("BoundReportSections", __base__=Strict,
        **{name: (list[finding], Field(min_length=field.metadata[0].min_length,
                                       max_length=next(rule.max_length for rule in field.metadata if hasattr(rule, "max_length"))))
           for name, field in ReportSections.model_fields.items()})
    return create_model(schema.__name__, __base__=Strict, sections=(sections, ...))


def canonical_draft(schema, draft, registry):
    """Derive local citations only from explicit, eligible, request-scoped parts.

    This is not a repair of raw prose or a relaxation of validate_findings.
    Complete internal tokens and their citations are constructed together;
    subsequent category, financial, numerical and privacy guards remain intact.
    """
    from app.core.exceptions import ApiError

    result = draft.model_dump()
    findings = result["answer"] if "answer" in result else [item for section in result["sections"].values() for item in section]
    for finding in findings:
        declared = finding["evidence_ids"]
        if not isinstance(declared, list) or any(not isinstance(key, str) or key not in registry or registry[key].get("id") != key for key in declared):
            raise ApiError("unsupported_ai_citation", "The generated research contained unsupported source references.", 502)
        if finding["quantitative_claims"]:
            raise ApiError("unsupported_ai_claim", "Typed research cannot supply model-owned financial values.", 502)
        citations = list(dict.fromkeys(declared))
        prose = []
        for part in finding["explanation"]:
            if not isinstance(part, dict):
                raise ApiError("unsupported_ai_binding", "The research selected an unsupported reference type.", 502)
            kind = part.get("kind")
            if kind == "text":
                text = part.get("text")
                if set(part) != {"kind", "text"} or not isinstance(text, str) or "{" in text or "}" in text:
                    raise ApiError("unsupported_ai_binding", "Research text cannot supply raw evidence bindings.", 502,
                                   {"rule": "typed_text_binding_forbidden"})
                prose.append((kind, text))
                continue
            if not isinstance(kind, str) or kind not in {"value", "date", "period", "model"} or set(part) != {"kind", "evidence_id"}:
                raise ApiError("unsupported_ai_binding", "The research selected an unsupported reference type.", 502,
                               {"rule": "unknown_typed_binding_kind"})
            key = part["evidence_id"]
            item = registry.get(key) if isinstance(key, str) else None
            if item is None or item.get("id") != key:
                raise ApiError("unsupported_ai_binding", "The research referenced evidence outside this request.", 502,
                               {"rule": "unknown_or_out_of_scope_typed_binding", "binding_kind": kind})
            if kind not in binding_kinds(item):
                raise ApiError("unsupported_ai_binding", "The research selected evidence ineligible for this reference type.", 502,
                               {"rule": "ineligible_typed_binding", "binding_kind": kind, "evidence_id": key})
            if key not in citations:
                citations.append(key)
            prose.append((kind, "{{" + kind + ":" + key + "}}"))
        if not citations:
            raise ApiError("unsupported_ai_citation", "The generated finding has no supported source references.", 502)
        if len(citations) > 12:
            raise ApiError("ai_render_limit", "The research finding exceeds the permitted source limit.", 502)
        finding["evidence_ids"] = citations
        finding["explanation"] = _join_segments(prose)
    return schema.model_validate(result)
