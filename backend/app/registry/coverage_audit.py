"""Read-only aggregate listing counts and bounded financial coverage matrices.

No provider access, financial calculation, or inference from a directory count.
"""
from collections import Counter
from datetime import date, datetime, timedelta
from html import escape

from sqlalchemy import func, select

from app.models.security_registry import (SecurityInstrument, SecurityIssuer, SecurityListing,
                                          SecurityListingObservation, SecurityRegistryRefresh)
from app.models.company import Company
from app.models.financial_fact import FinancialSnapshot
from app.core.database import as_utc
from app.registry.repository import _public_reference
from app.schemas.coverage import CoverageResponse

MODES = {"real_verified", "retained_public", "synthetic", "mocked"}


def registry_counts(session_factory, *, as_of: date, data_mode, max_age_days=1):
    """SQL aggregates; no original financial facts or full source JSON loaded."""
    if data_mode not in MODES:
        raise ValueError("Registry counts require an explicit data mode.")
    if not 0 <= max_age_days <= 366:
        raise ValueError("Listing age must be a bounded explicit calendar-day policy.")
    cutoff = (as_of - timedelta(days=max_age_days)).isoformat()
    proof = SecurityListing.verification
    verified = (proof["status"].as_string() == "verified",
                proof["confidence"].as_string() == "source_backed",
                SecurityListing.listing_status == "active",
                proof["observed_on"].as_string() <= as_of.isoformat())
    current = (*verified, proof["observed_on"].as_string() >= cutoff,
               proof["observed_on"].as_string() <= as_of.isoformat())
    with session_factory() as session:
        def count(*where):
            return session.scalar(select(func.count()).select_from(SecurityListing).where(*where))
        total = count()
        form_rows = session.execute(select(SecurityInstrument.security_form, func.count())
            .select_from(SecurityListing).join(SecurityInstrument)
            .where(*verified).group_by(SecurityInstrument.security_form)).all()
        all_forms = dict(session.execute(select(SecurityInstrument.security_form, func.count())
            .select_from(SecurityListing).join(SecurityInstrument)
            .group_by(SecurityInstrument.security_form)).all())
        statuses = dict(session.execute(select(SecurityListing.listing_status, func.count())
            .group_by(SecurityListing.listing_status)).all())
        identities = dict(session.execute(select(SecurityListing.identity_status, func.count())
            .group_by(SecurityListing.identity_status)).all())
        refreshes = session.execute(select(SecurityRegistryRefresh.source,
            func.max(SecurityRegistryRefresh.as_of), func.max(SecurityRegistryRefresh.retrieved_at),
            func.count()).group_by(SecurityRegistryRefresh.source)).all()
        verified_reits = session.scalar(select(func.count()).select_from(SecurityListing)
            .join(SecurityInstrument).join(SecurityIssuer)
            .where(*verified, SecurityIssuer.business_category == "reit"))
        observations = session.scalar(select(func.count()).select_from(SecurityListingObservation))
        financial_issuers = session.scalar(select(func.count(func.distinct(Company.issuer_id)))
            .select_from(Company).join(FinancialSnapshot))
        verified_financial_listings = session.scalar(select(func.count(func.distinct(SecurityListing.id)))
            .select_from(SecurityListing).join(SecurityInstrument)
            .join(Company, Company.issuer_id == SecurityInstrument.issuer_id)
            .join(FinancialSnapshot).where(*verified))
        return {"audit_version": "listing-coverage-1", "as_of": as_of.isoformat(), "data_mode": data_mode,
                "listing_freshness_policy": {"maximum_calendar_age_days": max_age_days,
                    "note": "A calendar-age policy is not a trading-calendar or continuous-trading guarantee."},
                "listing_denominator": total, "source_observation_count": observations,
                "verified_active_observations": count(*verified),
                "current_verified_active_observations": count(*current),
                "verified_identity_count": count(SecurityListing.identity_status == "verified"),
                "conflicting_listing_count": count(proof["status"].as_string() == "conflicting"),
                "future_source_observation_count": count(proof["observed_on"].as_string() > as_of.isoformat()),
                "listing_status_counts": dict(sorted(statuses.items())),
                "identity_status_counts": dict(sorted(identities.items())),
                "verified_active_security_form_counts": dict(sorted(form_rows)),
                "all_listing_security_form_counts": dict(sorted(all_forms.items())),
                "unknown_classification_count": all_forms.get("unknown", 0),
                "verified_active_reit_listings": verified_reits,
                "retained_financial_issuer_count": financial_issuers,
                "verified_listings_with_retained_issuer_snapshots": verified_financial_listings,
                "sources": [{"source": source, "latest_observed_on": observed.isoformat(),
                             "latest_retrieved_at": as_utc(retrieved).isoformat(), "retained_snapshots": number}
                            for source, observed, retrieved, number in sorted(refreshes)],
                "financial_coverage": "Not inferred: retained issuer snapshots do not establish selected-class compatibility or eligible models; use a separate financial sample.",
                "limitations": ["Directory rows, active listings, financial statements and eligible models have different denominators.",
                    "Verified active means a dated authoritative observation; absence is not a delisting."]}


def financial_matrix(bundle):
    """One explicit data mode per denominator, with financial source age retained."""
    _public_reference(bundle)
    mode = bundle.get("data_mode")
    if mode not in MODES:
        raise ValueError("An explicit supported data mode is required.")
    as_of = datetime.fromisoformat(bundle["as_of"].replace("Z", "+00:00"))
    if as_of.tzinfo is None:
        raise ValueError("Audit timestamps must include a timezone.")
    samples = bundle.get("samples")
    if not isinstance(samples, list) or not 1 <= len(samples) <= 10000:
        raise ValueError("A non-empty bounded financial sample is required.")
    rows, seen = [], set()
    for sample in samples:
        if sample.get("data_mode") != mode:
            raise ValueError("Real, retained, synthetic and mocked denominators must be separate.")
        coverage = CoverageResponse.model_validate(sample["coverage"]).model_dump(mode="json")
        observed = datetime.fromisoformat(coverage["as_of"].replace("Z", "+00:00"))
        if observed.tzinfo is None or observed > as_of:
            raise ValueError("Sample timestamps must be zoned and cannot follow the audit.")
        identity, stages = coverage["identity"] or {}, coverage["stages"]
        key = identity.get("listing_id") or identity.get("instrument_id")
        if not key or key in seen:
            raise ValueError("Every sample needs a unique stable security identity.")
        seen.add(key)
        proof = identity.get("listing_verification") or {}
        if mode == "real_verified" and (proof.get("status") != "verified" or
                proof.get("confidence") != "source_backed" or not proof.get("record_hash") or
                not proof.get("observed_on") or not proof.get("source")):
            raise ValueError("Real verified samples require retained source-backed listing proof.")
        value = stages["valuation"]
        number = value.get("contributing_model_count")
        if number is not None and (type(number) is not int or not 0 <= number <= 11):
            raise ValueError("Contributing model count must be an exact engine count or null.")
        blockers = [{"stage": name, "codes": part.get("reason_codes", []), "reason": part["reason"]}
                    for name, part in stages.items() if part["status"] != "available"]
        rows.append({"symbol": sample["requested_symbol"], "issuer": identity.get("issuer_id"),
            "cik": identity.get("cik"), "instrument_id": identity.get("instrument_id"), "listing_id": key,
            "exchange": identity.get("exchange"), "security_form": identity.get("security_form", identity.get("instrument_type")),
            "issuer_business_category": identity.get("issuer_business_category"),
            "listing_status": identity.get("listing_status"), "verification": proof,
            "reference_as_of": identity.get("registry_as_of"),
            "reference_sources": sorted({part["provider"] for part in identity.get("source_refs", [])
                                          if isinstance(part, dict) and isinstance(part.get("provider"), str)}),
            "financial_data_mode": sample.get("financial_data_mode", mode),
            "financial_source_dates": sample.get("financial_source_dates", {}),
            "statements": stages["statements"]["status"], "normalization": stages["normalization"]["status"],
            "share_basis": stages["share_basis"]["status"], "valuation": value["status"],
            "eligible_models": value.get("eligible_models"), "contributing_model_count": number,
            "confidence": value.get("confidence"), "quality": value.get("quality"),
            "ai_evidence_available": stages["ai_research"].get("evidence_available"),
            "stages": stages, "blockers": blockers})
    rows.sort(key=lambda item: item["symbol"])
    stage_names = CoverageResponse.model_fields["stages"].annotation.model_fields
    return {"audit_version": "financial-coverage-2", "as_of": bundle["as_of"], "data_mode": mode,
            "sample_denominator": len(rows),
            "issuer_denominator": len({row["issuer"] for row in rows if row["issuer"] and row["cik"]}),
            "unresolved_issuer_listing_count": sum(not row["cik"] for row in rows),
            "stage_status_counts": {name: dict(sorted(Counter(row["stages"][name]["status"] for row in rows).items()))
                                    for name in stage_names},
            "securities_with_statements": sum(row["statements"] == "available" for row in rows),
            "securities_with_compatible_share_basis": sum(row["share_basis"] == "available" for row in rows),
            "securities_with_contributing_models": sum((row["contributing_model_count"] or 0) > 0 for row in rows),
            "samples": rows,
            "limitations": ["Sample coverage is not whole-market financial coverage.",
                "Retained statements and quotes remain dated even when listing evidence is refreshed.",
                "A null model count means not assessed, never zero; AI evidence is not a generated AI report."]}


def markdown_matrix(report):
    def cell(value):
        if value is None:
            return "Not assessed"
        return escape(str(value), quote=False).replace("|", "&#124;").replace("\n", " ").replace("\r", " ")
    lines = [f"Financial sample: {report['sample_denominator']} securities; mode: {report['data_mode']}; as of {report['as_of']}.", "",
        "| Symbol | Issuer / CIK | Exchange | Instrument type | Listing status | Verification source/date | Financial-statement coverage | Compatible share basis | Valuation eligibility | Contributing model count | Confidence | Main blocker |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for row in report["samples"]:
        proof = row["verification"]
        source_date = (f"{proof['source']} / {proof['observed_on']}" if proof.get("source") and proof.get("observed_on")
                       else "Unverified; " + ", ".join(row.get("reference_sources") or ["reference source unknown"])
                       + " reference / " + (row.get("reference_as_of") or "unknown date"))
        blocker = next((part for part in row["blockers"] if part["stage"] == "valuation"), next(iter(row["blockers"]), None))
        fields = [row["symbol"], row["cik"] or "Unresolved", row["exchange"], row["security_form"],
            row["listing_status"], source_date,
            row["statements"] + " (" + row["financial_data_mode"] + ")", row["share_basis"],
            row["valuation"], row["contributing_model_count"], row["confidence"],
            ", ".join(blocker["codes"]) or blocker["reason"] if blocker else "None reported"]
        lines.append("| " + " | ".join(cell(value) for value in fields) + " |")
    return "\n".join(lines) + "\n"
