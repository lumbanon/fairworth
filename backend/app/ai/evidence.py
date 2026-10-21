"""Deterministic public evidence records; this module makes no network requests."""
from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
import math
import re
from urllib.parse import unquote, urlsplit, urlunsplit


CATEGORIES = frozenset({"reported_fact", "historical_metric", "valuation_output", "policy_estimate",
                        "user_assumption", "filing_excerpt", "company_profile", "unavailable"})
SECURITY_IDENTITY_FIELDS = ("issuer_id", "instrument_id", "listing_id", "cik", "ticker", "exchange",
                            "instrument_type", "listing_status", "identity_status", "share_class",
                            "registry_as_of", "registry_retrieved_at", "registry_version", "registry_status",
                            "security_form", "issuer_business_category", "verification_state")
LISTING_PROOF_FIELDS = ("status", "confidence", "source", "observed_on", "effective_on", "published_at",
                        "source_timezone", "record_hash", "parser_version", "version")
_VOLATILE_KEYS = frozenset({"generated_at", "calculated_at", "retrieved_at", "expires_at"})
_SOURCE_PATHS = {
    "data.sec.gov": ("/api/xbrl/companyfacts/", "/submissions/"),
    "www.sec.gov": ("/Archives/edgar/data/", "/ixviewer/"),
    "home.treasury.gov": ("/resource-center/data-chart-center/interest-rates/", "/treasury-daily-interest-rate-xml-feed"),
    "financialmodelingprep.com": ("/stable/", "/api/"),
    "www.nasdaqtrader.com": ("/dynamic/SymDir/nasdaqlisted.txt", "/dynamic/SymDir/otherlisted.txt"),
}


def json_value(value):
    """Copy only bounded JSON-compatible data, never implicit object reprs."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if hasattr(value, "model_dump"):
        return json_value(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_value(item) for item in value]
    return None


def stable_snapshot_id(value, prefix="snapshot"):
    """Retrieval/calculation clocks do not invalidate unchanged source snapshots."""
    def stable(item):
        if isinstance(item, dict):
            return {key: stable(part) for key, part in item.items() if key not in _VOLATILE_KEYS}
        if isinstance(item, list):
            return [stable(part) for part in item]
        return item
    serialized = json.dumps(stable(json_value(value)), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return f"{prefix}_{hashlib.sha256(serialized.encode('utf-8')).hexdigest()[:32]}"


def context_token_upper_bound(value):
    """UTF-8 bytes bound byte-tokenizer input conservatively, including JSON keys."""
    return len(json.dumps(json_value(value), ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8"))


def safe_source_url(value):
    """Only existing, public provider URLs; never credentialed URLs or invented links."""
    if not isinstance(value, str) or len(value) > 1000 or any(char.isspace() for char in value):
        return None
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        decoded = unquote(parsed.path)
        if (parsed.scheme != "https" or host not in _SOURCE_PATHS or parsed.username or parsed.password
                or parsed.port not in (None, 443) or parsed.query or parsed.fragment
                or "\\" in decoded or any(part in {".", ".."} for part in decoded.split("/"))
                or not any(decoded.startswith(prefix) for prefix in _SOURCE_PATHS[host])
                or host == "www.nasdaqtrader.com" and decoded not in _SOURCE_PATHS[host]):
            return None
        return urlunsplit(("https", host, parsed.path, "", ""))
    except ValueError:
        return None


def public_text(value, limit=600):
    """Keep retrieved text untrusted while stripping obvious contact/secret material."""
    if value is None:
        return None
    if not isinstance(value, (str, int, float, bool, date, datetime)):
        return None
    text = str(value)
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[contact redacted]", text)
    text = re.sub(r"(?i)(?:postgres(?:ql)?(?:\+\w+)?|mysql|mongodb)://\S+", "[private connection redacted]", text)
    text = re.sub(r"(?i)(?:sk-[A-Za-z0-9_-]{12,}|(?:api[_-]?key|authorization|password)\s*[:=]\s*\S+)", "[credential redacted]", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    return text[:limit]


def warning_texts(items):
    result = []
    for item in items or []:
        text = public_text(item.get("message") if isinstance(item, dict) else item, 350)
        if text and text not in result:
            result.append(text)
    return result


def security_identity(company):
    """Only public, resolved identifiers; no inferred identity from ticker text."""
    if not isinstance(company, dict) or not company.get("instrument_id"):
        return None
    result = {key: public_text(company.get(key), 150) for key in SECURITY_IDENTITY_FIELDS
              if key in company or key not in {"security_form", "issuer_business_category", "verification_state"}}
    expiry = company.get("proof_expiry")
    if isinstance(expiry, dict):
        result["proof_expiry"] = {
            kind: {key: public_text(record.get(key), 200) for key in
                   ("state", "source", "observed_on", "published_at", "source_timezone", "retrieved_at",
                    "policy_anchor_at", "expires_at", "ttl_seconds", "reason")}
            for kind, record in expiry.items() if kind in {"listing", "issuer_linkage"} and isinstance(record, dict)}
    proof = company.get("listing_verification")
    if isinstance(proof, dict):
        # Identity contains the exact observation/version, not an unbounded source
        # document. Retrieval clocks do not make a listing observation current.
        result["listing_verification"] = {key: public_text(proof.get(key), 200) for key in LISTING_PROOF_FIELDS}
        linkage = proof.get("issuer_linkage")
        if isinstance(linkage, dict):
            result["listing_verification"]["issuer_linkage"] = {
                key: public_text(linkage.get(key), 200) for key in
                ("source", "observed_on", "registry_version", "record_hash", "ticker", "cik", "exchange_mic", "status", "freshness")}
            result["listing_verification"]["issuer_linkage"]["stale"] = linkage.get("stale") if isinstance(linkage.get("stale"), bool) else None
    return result


def same_security(left, right):
    """A stable identity must not disappear when crossing a service boundary."""
    if left.get("cik") != right.get("cik"):
        return False
    return all(left.get(key) == right.get(key) for key in ("issuer_id", "instrument_id", "listing_id",
               "security_form", "issuer_business_category", "listing_verification", "verification_state", "proof_expiry")
               if left.get(key) is not None or right.get(key) is not None)


def period_label(value):
    if not value:
        return None
    if isinstance(value, str):
        return public_text(value, 140)
    if not isinstance(value, dict):
        return None
    years = value.get("fiscal_years")
    if isinstance(years, list) and years:
        return "FY " + ", ".join(str(year) for year in years[:12])
    start = value.get("start_date", value.get("start"))
    end = value.get("end_date", value.get("end"))
    fiscal = f"FY{value['fiscal_year']} {value.get('fiscal_period', '')}".strip() if value.get("fiscal_year") else ""
    dates = f"{start or 'unknown start'} to {end}" if end else ""
    return public_text("; ".join(part for part in (fiscal, dates) if part), 140) or None


class EvidenceRegistry:
    """Small immutable-value registry, deterministically ordered by insertion."""

    def __init__(self, ticker, identity=None):
        self.ticker = ticker
        self.identity = security_identity(identity)
        self.registry = {}

    def add(self, *, category, provider, title, metric, value, unit="text", period=None,
            observation_date=None, retrieved_at=None, source_url=None, accession=None,
            derivation=None, quality_warnings=None, excerpt=None):
        if category not in CATEGORIES:
            raise ValueError("Unsupported evidence category.")
        item = {"category": category, "provider": public_text(provider, 100) or "Fairworth",
                "title": public_text(title, 180) or "Evidence", "ticker": self.ticker,
                "metric": public_text(metric, 120) or "evidence", "value": json_value(value),
                "unit": public_text(unit, 50) or "unknown", "period": period_label(period),
                "observation_date": public_text(observation_date, 40), "retrieved_at": public_text(retrieved_at, 40),
                "source_url": safe_source_url(source_url), "accession": public_text(accession, 100),
                "derivation": public_text(derivation, 700), "quality_warnings": warning_texts(quality_warnings)[:8],
                "excerpt": public_text(excerpt, 4500)}
        if self.identity:
            item["identity"] = json_value(self.identity)
        identifier = stable_snapshot_id(item, "e")
        item = {"id": identifier, **item}
        self.registry.setdefault(identifier, item)
        return identifier
