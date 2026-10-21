"""Date and qualify immutable engine outputs without changing model decisions.

An intrinsic calculation and a current quoted-security publication have different
evidence requirements. This module supplies metadata only, never missing inputs.
"""
from copy import deepcopy
from datetime import UTC, date, datetime
import math

from app.valuation.financial_currentness import assess_financial_currentness


def _instant(value):
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(UTC) if parsed.tzinfo else None
    except (TypeError, ValueError):
        return None


def _day(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _current_proof(proof, clock):
    observed, expiry = _day(proof.get("observed_on")), _instant(proof.get("expires_at"))
    retrieved = _instant(proof.get("retrieved_at"))
    return bool(proof.get("state") == "verified" and proof.get("source")
                and observed and observed <= clock.date() and expiry and clock <= expiry
                and retrieved and retrieved <= clock)


def publication_status(inputs, case, checks, clock):
    """Preserve the scalar result and separately state whether it is current.

    Registry freshness has already been evaluated against exact source scope by
    SecurityRegistryService. Recheck its fixed expiry at calculation time so a
    cached snapshot cannot cross the policy boundary as a current publication.
    Financial freshness is the existing source-cache status, not retrieval time
    substituted for a reporting or filing date. No new TTL is introduced here.
    """
    company, financial = inputs.get("company", {}), inputs.get("financial_source_status") or {}
    expiry = company.get("proof_expiry") or {}
    quote = inputs.get("market") or {}
    period = inputs.get("reporting_period") or {}
    facts = inputs.get("facts") or {}
    filings = sorted({str(item["filed"]) for fact in facts.values() if isinstance(fact, dict)
                      for item in fact.get("provenance", []) if isinstance(item, dict) and item.get("filed")})
    blockers = []

    def block(code, message):
        blockers.append({"code": code, "message": message})

    exact_identity = all(company.get(key) for key in ("issuer_id", "instrument_id", "listing_id", "cik"))
    if not exact_identity or company.get("identity_status") != "verified":
        block("current_security_identity_unverified", "Current publication requires the exact verified issuer, instrument and listing identity.")
    for kind, label in (("listing", "listing observation"), ("issuer_linkage", "issuer-symbol linkage")):
        proof = expiry.get(kind) or {}
        if not _current_proof(proof, clock):
            code = "verification_expired" if proof.get("state") == "verification_expired" or (
                _instant(proof.get("expires_at")) and clock > _instant(proof["expires_at"])) else "verification_unavailable"
            block(f"{kind}_{code}", f"The original {label} is expired or unverified; financial and quote retrieval cannot renew it.")
    if company.get("verification_state") != "verified" or company.get("listing_status") != "active":
        block("current_active_security_unverified", "The selected security does not have independently current active-listing and ownership proofs.")
    if financial.get("status") != "fresh":
        block("financial_source_currentness_unverified", "The financial source has no independently fresh source-cache assessment; its reported observations remain dated.")
    currentness = assess_financial_currentness(inputs, clock)
    if currentness["status"] != "current":
        block("financial_period_currentness_unverified", currentness["reason"])
    reporting_end = _day(period.get("end_date"))
    filed_days = [_day(item) for item in filings]
    financial_retrieved = _instant(inputs.get("financial_retrieved_at"))
    if not reporting_end or reporting_end > clock.date() or not filed_days or any(
            day is None or day > clock.date() or day < reporting_end for day in filed_days):
        block("financial_source_dates_unverified", "A supported reporting period and compatible filing dates at or before the calculation clock are required.")
    if (financial_retrieved is None or financial_retrieved > clock
            or any(day and day > financial_retrieved.date() for day in filed_days)):
        block("financial_acquisition_clock_unverified", "The original financial acquisition clock must be recorded at or before calculation and cannot precede the filing evidence.")
    for key, code in (("share_basis", "publication_share_basis_unverified"),
                      ("currency", "publication_currency_unverified"),
                      ("reporting_regime", "publication_reporting_regime_unverified")):
        if checks.get(key, {}).get("status") != "available":
            block(code, checks.get(key, {}).get("reason") or "Compatible reported financial evidence is unavailable.")
    quote_observed, quote_retrieved = _instant(quote.get("price_timestamp")), _instant(quote.get("retrieved_at"))
    if (checks.get("market_price", {}).get("status") != "available" or not quote.get("provider")
            or quote_observed is None or quote_retrieved is None or not quote_observed <= quote_retrieved <= clock):
        block("current_provider_quote_unavailable", "A valid compatible provider quote within the existing observation-age policy is required; manual prices do not establish this.")
    # User assumptions remain useful scenario outputs but are never promoted to
    # source-verified current default results by a current comparison quote.
    if case.get("summary", {}).get("classification") == "user_defined":
        block("user_defined_scenario", "The result includes explicit user assumptions and remains an illustrative scenario.")
    value = case.get("summary", {}).get("fair_value")
    result_type = ("unavailable" if not _finite(value) else "historical_illustration" if blockers else "current_eligible")
    if result_type == "unavailable":
        block("no_eligible_model_output", "The deterministic engine produced no contributing fair-value output for this scenario.")
    return {"result_type": result_type, "current_eligible": result_type == "current_eligible",
            "blockers": blockers, "financial_currentness": currentness,
            "clocks": {"calculated_at": clock.isoformat(), "listing": deepcopy(expiry.get("listing") or {}),
                       "issuer_linkage": deepcopy(expiry.get("issuer_linkage") or {}),
                       "quote": {"observed_at": quote.get("price_timestamp"), "retrieved_at": quote.get("retrieved_at"),
                                 "provider": quote.get("provider"), "source_status": quote.get("status")},
                       "financial": {"reporting_period": deepcopy(period), "filed_at": filings,
                                     "retrieved_at": inputs.get("financial_retrieved_at"), "source_status": financial.get("status")}},
            "limitations": ["Result type qualifies publication currentness and never changes the intrinsic calculation or model eligibility.",
                            "Historical illustration describes dated or scenario evidence, not a claim that the estimate was published at an earlier date."]}
