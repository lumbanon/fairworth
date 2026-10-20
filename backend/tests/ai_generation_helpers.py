"""Encode canonical offline mocks in the generation-only typed-parts contract.

This fixture adapter never validates, formats or repairs financial claims. Source
values remain server-owned; legacy exact-claim fixtures select their evidence ID
instead of asking a mocked model to reproduce financial values or metadata.
"""
from copy import deepcopy
import json
import re


_TOKEN = re.compile(r"\{\{(value|date|period|model|claim):([A-Za-z0-9_-]+)\}\}", re.ASCII)


def _parts(finding):
    explanation = finding["explanation"]
    if isinstance(explanation, list):
        return deepcopy(explanation)
    parts, cursor, selected = [], 0, set()
    quantities = finding.get("quantitative_claims", [])
    for match in _TOKEN.finditer(explanation):
        if match.start() > cursor:
            parts.append({"kind": "text", "text": explanation[cursor:match.start()]})
        kind, identifier = match.groups()
        if kind == "claim":
            index = int(identifier)
            assert 0 <= index < len(quantities), "Invalid legacy mock claim index"
            kind, identifier = "value", quantities[index]["evidence_id"]
        parts.append({"kind": kind, "evidence_id": identifier})
        if kind == "value":
            selected.add(identifier)
        cursor = match.end()
    if cursor < len(explanation):
        parts.append({"kind": "text", "text": explanation[cursor:]})
    for quantity in quantities:
        if quantity["evidence_id"] not in selected:
            parts.extend([{"kind": "text", "text": " Evidence-backed observation: "},
                          {"kind": "value", "evidence_id": quantity["evidence_id"]}])
            selected.add(quantity["evidence_id"])
    return parts


def generation_payload(draft):
    """Return JSON-compatible typed mock output without mutating its source."""
    result = deepcopy(draft.model_dump() if hasattr(draft, "model_dump") else draft)
    findings = result["answer"] if "answer" in result else [item for section in result["sections"].values() for item in section]
    for finding in findings:
        finding["explanation"] = _parts(finding)
        finding["quantitative_claims"] = []
    return result


def generation_json(draft):
    return json.dumps(generation_payload(draft), ensure_ascii=False)
