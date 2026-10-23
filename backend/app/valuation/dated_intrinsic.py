"""Explicit, source-bound historical common-dividend scenario scope.

An archived listing proof can support a dated scenario without renewing today's
identity. The original company and publication metadata remain unchanged.
"""
from copy import deepcopy
from datetime import UTC, datetime, time, timedelta
import re

from app.core.exceptions import ApiError
from app.services.security_identity import applicability, same_identity

VERSION = "dated-common-dividend-scenario-1"
FIELDS = {"cost_of_equity", "dividend_growth", "stable_dividend_confirmed"}


def _instant(raw):
    try:
        value = raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return value.astimezone(UTC) if value.tzinfo else None
    except (TypeError, ValueError):
        return None


def request_scope(request):
    if request.context != "dated_intrinsic":
        return
    if (request.enabled_models != ["dividend"] or set(request.assumptions) != FIELDS
            or request.assumptions.get("stable_dividend_confirmed") is not True
            or any(value is None for value in request.assumptions.values())
            or request.manual_market_price is not None or request.discount_rates is not None
            or any(set(edits) - FIELDS for edits in request.scenario_overrides.values())):
        raise ApiError("invalid_dated_intrinsic_request", "The dated intrinsic workflow requires only Dividend Discount Model, explicit growth, required return and payout-sustainability confirmation, with no market price or financial-fact overrides.", 422)


def prepare_dated_intrinsic(inputs, request, *, clock=None):
    """Validate server-owned retained records; request supplies only the clock."""
    request_scope(request)
    now = _instant(clock or datetime.now(UTC))
    selected = _instant(request.evidence_as_of)
    if selected is None or now is None or selected > now:
        raise ApiError("invalid_dated_evidence_clock", "A nonfuture, timezone-aware evidence clock is required.", 422)
    original = inputs.get("company") or {}
    archived = inputs.get("archived_identity_evidence")
    if archived is not None:
        scope_fields = ("issuer_id", "instrument_id", "listing_id", "cik", "ticker", "exchange_mic", "security_form", "listing_status")
        if (not isinstance(archived, dict) or not same_identity(original, archived)
                or any(not archived.get(field) or archived[field] != original.get(field) for field in scope_fields)
                or not re.fullmatch(r"[0-9a-f]{64}", str(archived.get("package_hash") or ""))
                or not isinstance(archived.get("source_inventory"), list) or len(archived["source_inventory"]) != 2):
            raise ApiError("dated_security_scope_unverified", "The approved archived reference attachment does not match this exact selected security.", 422)
        # Only archived proof fields enter historical eligibility. Today's
        # installed company/registry state stays in inputs and publication.
        original = deepcopy(original)
        for field in ("listing_verification", "issuer_linkage", "proof_expiry"):
            original[field] = deepcopy(archived.get(field) or {})
    listing = original.get("listing_verification") or {}
    linkage = original.get("issuer_linkage") or listing.get("issuer_linkage") or {}
    if (not all(original.get(field) for field in ("issuer_id", "instrument_id", "listing_id", "cik", "ticker", "exchange_mic"))
            or original.get("identity_status") in {"ambiguous", "conflicting", "unresolved"}
            or original.get("listing_status") != "active" or listing.get("status") != "verified"
            or listing.get("conflicts") or original.get("security_form", original.get("instrument_type")) != "common_stock"
            or linkage.get("issuer_id") != original["issuer_id"] or linkage.get("cik") != original["cik"]
            or linkage.get("ticker") != original["ticker"] or linkage.get("exchange_mic") != original["exchange_mic"]):
        raise ApiError("dated_security_scope_unverified", "The historical scenario requires the exact unambiguous domestic common-share issuer, instrument, listing and SEC symbol linkage.", 422)
    retained = {}
    for kind, proof in (("listing", listing), ("issuer_linkage", linkage)):
        policy = (original.get("proof_expiry") or {}).get(kind) or {}
        retrieved, expiry = _instant(proof.get("retrieved_at")), _instant(policy.get("expires_at"))
        anchor = _instant(policy.get("policy_anchor_at"))
        fingerprint = proof.get("record_hash") or proof.get("registry_version")
        try:
            observed = datetime.combine(datetime.fromisoformat(proof["observed_on"]).date(), time.min, tzinfo=UTC)
            ttl = policy["ttl_seconds"]
        except (KeyError, TypeError, ValueError):
            observed, ttl = None, None
        if (not re.fullmatch(r"[0-9a-f]{64}", str(fingerprint or ""))
                or not proof.get("source") or not str(proof.get("source_url") or "").startswith("https://")
                or retrieved is None or expiry is None or anchor is None or observed != anchor
                or not isinstance(ttl, (float, int)) or isinstance(ttl, bool) or not 0 < ttl <= 86400
                or expiry != anchor + timedelta(seconds=ttl)
                or not observed <= retrieved <= selected < expiry
                or policy.get("source") != proof.get("source") or policy.get("observed_on") != proof.get("observed_on")
                or _instant(policy.get("retrieved_at")) != retrieved):
            raise ApiError("dated_security_proof_unverified", "The selected evidence clock must fall within the original source-backed listing and issuer-linkage validity intervals, after original retrieval.", 422)
        retained[kind] = {"source": proof["source"], "source_url": proof["source_url"], "source_hash": fingerprint,
                          "observed_on": proof["observed_on"], "retrieved_at": retrieved.isoformat(), "expires_at": expiry.isoformat()}
    profile = inputs.get("dated_share_basis_evidence") or {}
    profile_clock = _instant(profile.get("retrieved_at"))
    if (inputs.get("basis", {}).get("share_basis_verified") is not True
            or profile.get("cik") != original["cik"] or profile.get("ticker") != original["ticker"]
            or profile.get("has_multiple_share_classes") is not False
            or profile_clock is None or profile_clock > selected
            or not re.fullmatch(r"[0-9a-f]{64}", str(profile.get("source_hash") or ""))):
        raise ApiError("dated_share_basis_unverified", "A retained SEC profile and compatible selected common-share declaration are required; an unreviewed share class cannot be substituted.", 422)
    financial_clock = _instant(inputs.get("financial_retrieved_at"))
    fact = inputs.get("facts", {}).get("declared_common_dividend_per_share") or {}
    if (financial_clock is None or financial_clock > selected or fact.get("value") is None
            or not fact.get("provenance") or fact.get("unit") != f"{inputs.get('currency')}/shares"
            or any(_instant(str(record.get("filed")) + "T00:00:00Z") is None
                   or _instant(str(record.get("filed")) + "T00:00:00Z") > selected
                   or _instant(str(record.get("filed")) + "T00:00:00Z") > financial_clock
                   or record.get("cik") != original["cik"] for record in fact["provenance"])):
        raise ApiError("dated_financial_evidence_unverified", "A compatible source-backed annual common-share dividend and its original acquisition and filing clocks are required.", 422)
    historical = deepcopy(original)
    historical.update(identity_status="verified", registry_status="fresh", verification_state="verified")
    historical["listing_verification"].update(freshness="fresh", stale=False)
    historical["issuer_linkage"] = deepcopy(linkage)
    historical["issuer_linkage"].update(freshness="fresh", stale=False)
    if not same_identity(original, historical) or applicability(historical):
        raise ApiError("dated_security_scope_unverified", "The archived security remains incompatible with ordinary common-share valuation.", 422)
    result = deepcopy(inputs)
    result["market"] = None  # Historical financial scope never supplies a current quote.
    result["dated_intrinsic_scope"] = {"methodology_version": VERSION, "status": "verified", "context": "dated_intrinsic",
        "evidence_as_of": selected.isoformat(), "identity": {field: original[field] for field in ("issuer_id", "instrument_id", "listing_id", "cik", "ticker")},
        "identity_proof_origin": "approved_archived_reference_attachment" if archived else "retained_registry",
        "archived_package_hash": archived.get("package_hash") if archived else None,
        "proofs": retained, "share_basis_evidence": deepcopy(profile), "historical_identity": historical,
        "limitations": ["Archived proof is valid only at the selected evidence clock; current listing and publication states are unchanged.",
                        "The retained SEC profile described one listed ticker; it is dated adapter evidence, not proof that no unlisted class exists.",
                        "This is an explicit user-assisted dividend scenario, excluded from automatic default coverage."]}
    return result
