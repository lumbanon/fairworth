"""Deterministic field precedence over immutable, source-scoped observations."""
from app.core.database import as_utc
from app.registry.listing_sources import US_MICS, exchange_mic


def sec_issuer_linkage(*, ticker, venue, cik, issuer_id, observed_on, registry_version,
                       source, source_url, record_hash=None, retrieved_at=None, published_at=None):
    """An issuer-symbol clock is independent of exchange directory membership."""
    return {"source": source, "observed_on": str(observed_on), "registry_version": registry_version,
            "record_hash": record_hash, "source_url": source_url, "ticker": ticker,
            "retrieved_at": retrieved_at, "published_at": published_at,
            "exchange_mic": venue, "cik": cik, "issuer_id": issuer_id,
            "match_method": "exact_sec_symbol_venue_issuer"}


def latest_by_source(observations):
    latest = {}
    for observation in observations:
        previous = latest.get(observation.source)
        order = (observation.observed_on, as_utc(observation.retrieved_at), observation.id)
        if previous is None or order > (previous.observed_on, as_utc(previous.retrieved_at), previous.id):
            latest[observation.source] = observation
    return list(latest.values())


def project_listing(listing, instrument, issuer, observations):
    """Unknown reference fields cannot overwrite explicit exchange proof.

    Each source's latest assertion remains independently inspectable. Explicit
    disagreements between listing authorities block promotion, even if one is
    newer: without lifecycle evidence a convenient source cannot settle them.
    """
    linkage = (listing.verification or {}).get("issuer_linkage")
    authoritative = [item for item in latest_by_source(observations) if item.source_kind == "listing_authority"]
    if not authoritative:
        return
    selected = max(authoritative, key=lambda item: (item.observed_on, as_utc(item.retrieved_at), item.source))
    conflicts = []
    for field in ("listing_status", "security_form", "share_class", "exchange_mic"):
        values = {}
        for observation in authoritative:
            value = observation.record.get(field)
            if value not in (None, "", "unknown"):
                values.setdefault(str(value), []).append(observation.source)
        if len(values) > 1:
            conflicts.append({"field": field, "values": [{"value": value, "sources": sources}
                                                           for value, sources in sorted(values.items())]})
    record, meta = selected.record, selected.provenance
    form = record.get("security_form") or "unknown"
    mic = exchange_mic(record.get("exchange"), record.get("exchange_mic"))
    sourced = mic in US_MICS and record.get("listing_status") != "unknown" and bool(record.get("source_refs"))
    status = "conflicting" if conflicts else "verified" if sourced else "reference_only"
    listing.verification = {"status": status,
        "confidence": "conflicted" if conflicts else "source_backed" if sourced else "unverified",
        "source": selected.source, "observed_on": selected.observed_on.isoformat(),
        "published_at": selected.published_at, "source_timezone": meta.get("source_timezone"),
        "retrieved_at": as_utc(selected.retrieved_at).isoformat(), "record_hash": selected.record_hash,
        "source_url": meta.get("source_url"), "parser_version": meta.get("version"),
        "conflicts": conflicts, "warnings": record.get("warnings", []),
        "latest_source_observation_count": len(latest_by_source(observations)),
        "issuer_linkage": linkage,
        "sources": [{"source": item.source, "observed_on": item.observed_on.isoformat(),
                     "source_record_key": item.source_record_key, "published_at": item.published_at,
                     "source_timezone": item.provenance.get("source_timezone"),
                     "retrieved_at": as_utc(item.retrieved_at).isoformat(),
                     "record_hash": item.record_hash, "source_url": item.provenance.get("source_url"),
                     "original_record": item.record.get("original_record", {}),
                     "warnings": item.record.get("warnings", [])}
                    for item in authoritative]}
    listing.listing_status = "unknown" if conflicts else record["listing_status"]
    # A source directory has no CIK. Exact SEC symbol+venue linkage supplies the
    # issuer association; source membership alone cannot invent financial ownership.
    listing.identity_status = "conflicting" if conflicts else "verified" if sourced and issuer and issuer.cik and linkage else "reference_only"
    listing.exchange, listing.exchange_mic = record.get("exchange"), mic
    listing.display_symbol = record.get("display_symbol") or record["ticker"]
    listing.security_description = record.get("security_description")
    listing.source_security_identifier = record.get("source_security_identifier")
    listing.as_of, listing.refresh_id = selected.observed_on, selected.refresh_id
    instrument.security_form = "unknown" if any(item["field"] == "security_form" for item in conflicts) else form
    # Keep the compatibility field, while business applicability is separate.
    instrument.instrument_type = instrument.security_form
    instrument.classification_evidence = record.get("classification_evidence", {})
    instrument.share_class = record.get("share_class") or instrument.share_class

