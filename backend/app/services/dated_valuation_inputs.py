"""Read only an explicitly imported financial snapshot and retained SEC profile.

There is no cache loader or provider method in this path. Missing local evidence
is a user-visible limitation, never permission for a new source request.
"""
from copy import deepcopy

from sqlalchemy import select

from app.core.database import as_utc
from app.core.exceptions import ApiError
from app.models import CacheEntry
from app.repositories.financial_repository import content_hash
from app.services.security_identity import check_provider_identity
from app.valuation.inputs import build_valuation_inputs
from app.valuation.financial_currentness import source_cache_policy, unverified_currentness


def retained_profile(repository, identity):
    with repository.session_factory() as session:
        rows = session.scalars(select(CacheEntry).where(CacheEntry.key.startswith("sec:company:"),
            CacheEntry.payload["cik"].as_string() == identity["cik"], CacheEntry.payload["ticker"].as_string() == identity["ticker"])
            .order_by(CacheEntry.retrieved_at.desc()).limit(1000)).all()
        for row in rows:
            payload = row.payload
            if (row.provider not in {"sec", "sec-edgar"} or not isinstance(payload, dict)
                    or payload.get("ticker") != identity["ticker"] or payload.get("cik") != identity["cik"]
                    or payload.get("has_multiple_share_classes") is not False):
                continue
            check_provider_identity(identity, payload)
            return deepcopy(payload), {"source_type": "retained_sec_adapter_profile", "provider": row.provider,
                "cache_key": row.key, "source_hash": content_hash(payload),
                "retrieved_at": as_utc(row.retrieved_at).isoformat(),
                "cik": payload["cik"], "ticker": payload["ticker"],
                "has_multiple_share_classes": False,
                "source_url": f"https://data.sec.gov/submissions/CIK{identity['cik']}.json",
                "limitations": ["The SEC adapter observed one listed ticker. It does not establish absence of unlisted classes or current share count."]}
    raise ApiError("dated_share_basis_unavailable", "No compatible retained SEC company profile is available for this selected common share; this workflow will not fetch one.", 422)


def build_dated_inputs(registry, repository, settings, ticker, instrument_id=None, listing_id=None):
    raw_identity = registry.repository.resolve(ticker, instrument_id, listing_id)
    identity = registry._with_freshness(raw_identity)
    if not identity.get("issuer_id") or not identity.get("cik"):
        raise ApiError("dated_security_scope_unverified", "A retained stable issuer and listing identity are required.", 422)
    imported = repository.imported_dataset(identity["issuer_id"], identity["cik"])
    if imported is None:
        raise ApiError("dated_financial_import_required", "This provider-free historical workflow requires a separately approved SEC financial import. No database import or new source request is performed automatically.", 422)
    profile, profile_evidence = retained_profile(repository, identity)
    company = {**profile, **identity}
    inputs = build_valuation_inputs({"company": company, "market": None}, imported["payload"], imported["retrieved_at"])
    inputs["dated_share_basis_evidence"] = profile_evidence
    inputs["financial_import"] = deepcopy(imported["provenance"])
    archived = (imported.get("archived_security_proofs") or {}).get(identity["listing_id"])
    if archived:
        inputs["archived_identity_evidence"] = {
            **deepcopy(archived["identity"]),
            **{field: deepcopy(archived[field]) for field in ("listing_verification", "issuer_linkage", "proof_expiry", "source_inventory", "package_hash")},
        }
    inputs["data_status"] = "stale"
    inputs["financial_source_status"] = {"status": "stale", "currentness": unverified_currentness(),
        "source_cache": source_cache_policy(imported["retrieved_at"], settings.sec_cache_ttl_seconds,
                                             actual_expires_at=imported["expires_at"]),
        "reason": "Original imported financial and SEC profile clocks are retained. This path makes no provider requests."}
    return inputs
