"""A fresh document cache does not establish a current financial reporting basis.

Currentness needs a reviewed, source-backed determination of the latest applicable
filing. There is deliberately no production policy yet: a recent acquisition of
old facts must remain a historical illustration until that evidence is supported.
"""
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
import re
from urllib.parse import urlsplit


VERSION = "financial-currentness-1"
# A registered callable must validate source identity, source completeness and
# the applicable fiscal/reporting regime. Neither API request fields nor provider
# payload booleans can register a policy. Tests install clearly synthetic policies.
REVIEWED_FINANCIAL_CURRENTNESS_POLICIES = {}


def _instant(value):
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else None
    try:
        value = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return value.astimezone(UTC) if value.tzinfo else None
    except (TypeError, ValueError):
        return None


def _public_source(source):
    if not isinstance(source, dict) or not source.get("provider") or not re.fullmatch(r"[a-f0-9]{64}", str(source.get("document_hash", ""))):
        return False
    try:
        url = urlsplit(source.get("url", ""))
        return bool(url.scheme == "https" and url.hostname and not url.username and not url.password
                    and url.port in (None, 443) and not url.query and not url.fragment)
    except (TypeError, ValueError):
        return False


def unverified_currentness():
    return {"methodology_version": VERSION, "status": "unverified", "policy_id": None,
            "reason": "No reviewed source-backed assessment establishes the latest applicable financial reporting period; a fresh source cache alone is insufficient."}


def source_cache_policy(retrieved_at, ttl_seconds, *, actual_expires_at=None):
    """Record the existing configured cache boundary; never start a new clock."""
    observed = _instant(retrieved_at)
    ttl = ttl_seconds if isinstance(ttl_seconds, int) and not isinstance(ttl_seconds, bool) and ttl_seconds > 0 else None
    actual = _instant(actual_expires_at)
    configured = observed + timedelta(seconds=ttl) if observed and ttl else None
    return {"provider": "sec-edgar", "retrieved_at": observed.isoformat() if observed else None,
            "expires_at": min(actual, configured).isoformat() if actual and configured else None,
            "original_expires_at": actual.isoformat() if actual else None,
            "configured_expires_at": configured.isoformat() if configured else None,
            "ttl_seconds": ttl}


def assess_financial_currentness(inputs, clock):
    """Validate a server-owned assessment independently of cache availability."""
    financial = inputs.get("financial_source_status") or {}
    proof, cache = financial.get("currentness") or {}, financial.get("source_cache") or {}
    proof = proof if isinstance(proof, dict) else {}
    cache = cache if isinstance(cache, dict) else {}
    result = {"methodology_version": VERSION, "status": "unverified", "reason_codes": [],
              "assessment": deepcopy(proof), "source_cache": deepcopy(cache)}

    def reject(code):
        if code not in result["reason_codes"]:
            result["reason_codes"].append(code)

    retrieved, expiry = _instant(cache.get("retrieved_at")), _instant(cache.get("expires_at"))
    original_expiry = _instant(cache.get("original_expires_at"))
    configured_expiry = _instant(cache.get("configured_expires_at"))
    original_retrieval = _instant(inputs.get("financial_retrieved_at"))
    ttl = cache.get("ttl_seconds")
    valid_ttl = isinstance(ttl, int) and not isinstance(ttl, bool) and ttl > 0
    if (financial.get("status") != "fresh" or not valid_ttl or not retrieved or not expiry or not original_expiry
            or retrieved != original_retrieval or configured_expiry != retrieved + timedelta(seconds=ttl)
            or expiry != min(original_expiry, configured_expiry)
            or not retrieved <= clock < expiry or cache.get("provider") != "sec-edgar"):
        reject("financial_source_cache_expired_or_unverified")
    policy = REVIEWED_FINANCIAL_CURRENTNESS_POLICIES.get(proof.get("policy_id")) if isinstance(proof.get("policy_id"), str) else None
    if proof.get("status") != "current" or not callable(policy):
        reject("financial_currentness_policy_unavailable")
    assessed, valid_until = _instant(proof.get("assessed_at")), _instant(proof.get("valid_until"))
    if (not assessed or not valid_until or not expiry or not assessed <= clock < valid_until <= expiry
            or not retrieved or assessed < retrieved):
        reject("financial_currentness_assessment_expired_or_unverified")
    period, latest = inputs.get("reporting_period") or {}, proof.get("latest_applicable_period") or {}
    latest = latest if isinstance(latest, dict) else {}
    if (not period.get("start_date") or not period.get("end_date")
            or any(str(period.get(key)) != str(latest.get(key)) for key in ("start_date", "end_date"))):
        reject("financial_currentness_period_mismatch")
    filing = proof.get("filing") or {}
    filing = filing if isinstance(filing, dict) else {}
    records = [record for fact in (inputs.get("facts") or {}).values() if isinstance(fact, dict)
               for record in fact.get("provenance", []) if isinstance(record, dict)]
    if (not filing.get("accession") or filing.get("cik") != inputs.get("company", {}).get("cik")
            or filing.get("form") not in {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}
            or not any(record.get("accn") == filing["accession"] and str(record.get("filed")) == str(filing.get("filed_at"))
                       and str(record.get("end")) == str(period.get("end_date"))
                       for record in records)):
        reject("financial_currentness_filing_unverified")
    source = proof.get("source") or {}
    source = source if isinstance(source, dict) else {}
    observed, acquired = _instant(source.get("observed_at")), _instant(source.get("retrieved_at"))
    if (not _public_source(source) or not observed or not acquired or not assessed
            or not observed <= acquired <= assessed):
        reject("financial_currentness_source_unverified")
    try:
        filed = date.fromisoformat(str(filing.get("filed_at")))
        period_end = date.fromisoformat(str(period.get("end_date")))
    except ValueError:
        filed, period_end = None, None
    if not filed or not period_end or not observed or not period_end <= filed <= observed.date():
        reject("financial_currentness_filing_unverified")
    if callable(policy):
        try:
            supported = policy(inputs, proof, clock) is True
        except (KeyError, TypeError, ValueError):
            supported = False
        if not supported:
            reject("financial_currentness_policy_rejected")
    if not result["reason_codes"]:
        result["status"] = "current"
    result["reason"] = ("A reviewed source-backed assessment establishes this exact latest applicable filing and remains within the original source-cache boundary."
                        if result["status"] == "current" else
                        "Current financial reporting has not been established by a reviewed, unexpired source-backed assessment; cache freshness and recent retrieval do not establish it.")
    return result
