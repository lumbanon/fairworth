"""Atomic reference imports and bounded indexed SQL discovery.

CIK identifies a registrant, never a security class. Source instrument keys may
link a rename only when the importer supplies that relationship explicitly.
"""
from __future__ import annotations

from datetime import date
import hashlib
import json
import re
from urllib.parse import urlsplit

from fastapi.encoders import jsonable_encoder
from sqlalchemy import case, delete, exists, func, intersect, or_, select, union
from sqlalchemy.orm import defer

from app.core.database import as_utc, utcnow
from app.core.exceptions import ApiError
from app.models.security_registry import (SecurityAlias, SecurityInstrument, SecurityIssuer,
                                           SecurityListing, SecurityRegistryRefresh, SecurityListingObservation, identifier)
from app.registry.schemas import RegistryProvenance, RegistryRecord
from app.registry.listing_sources import exchange_mic
from app.registry.verification import project_listing, sec_issuer_linkage


def normalized(value):
    return " ".join(str(value).strip().upper().split())


def source_key(source, kind, *parts):
    material = json.dumps([source, kind, *parts], separators=(",", ":"))
    return f"{source[:80]}:{kind}:" + hashlib.sha256(material.encode()).hexdigest()


def _prefix(value):
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _public_reference(value):
    """Reference imports have no legitimate credential/contact fields."""
    forbidden = {"apikey", "api_key", "password", "authorization", "secret", "token", "email",
                 "user_agent", "database_url", "openai_api_key", "fmp_api_key"}
    if isinstance(value, dict):
        if any(str(key).lower() in forbidden for key in value):
            raise ValueError("Security reference data cannot contain credentials or contact fields.")
        for key, child in value.items():
            if str(key).lower() in {"url", "source_url"} and child is not None:
                try:
                    address = urlsplit(str(child))
                    safe = (address.scheme == "https" and bool(address.hostname) and not address.username
                            and not address.password and address.port in (None, 443) and not address.query and not address.fragment)
                except ValueError:
                    safe = False
                if not safe:
                    raise ValueError("Security reference URLs must be public HTTPS paths without credentials, queries or fragments.")
        for child in value.values():
            _public_reference(child)
    elif isinstance(value, list):
        for child in value:
            _public_reference(child)
    elif isinstance(value, str) and (re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", value, re.I)
                                    or re.search(r"[A-Z][A-Z0-9+.-]*://[^/\s]*:[^/\s]*@", value, re.I)
                                    or re.search(r"(?:api[_-]?key|password|token)=", value, re.I)):
        raise ValueError("Security reference data cannot contain credentials or contact information.")


class SecurityRegistryRepository:
    def __init__(self, session_factory, *, max_source_snapshots=128, max_observations=2_000_000):
        self.session_factory = session_factory
        if not 1 <= int(max_source_snapshots) <= 10000 or not 1 <= int(max_observations) <= 10_000_000:
            raise ValueError("Administrative registry history budgets exceed supported bounds.")
        self.max_source_snapshots, self.max_observations = int(max_source_snapshots), int(max_observations)

    def has_records(self):
        with self.session_factory() as session:
            return session.scalar(select(SecurityListing.id).limit(1)) is not None

    def import_snapshot(self, records, provenance):
        """Import already authorized data; never fetch, merge by name, or delete.

        Full original validated records remain in the refresh for reproducible
        history. Even a complete snapshot does not infer delistings: changes
        must be explicit dated records from the source.
        """
        meta = RegistryProvenance.model_validate(provenance)
        rows = [RegistryRecord.model_validate(row) for row in records]
        if not rows:
            raise ValueError("A reference snapshot must contain at least one record.")
        if len(rows) > 100000:
            raise ValueError("A reference snapshot exceeds the bounded import size.")
        for row in rows:
            if row.valid_from and row.valid_to and row.valid_from > row.valid_to:
                raise ValueError("Listing validity interval is reversed.")
            if row.identity_status == "verified" and not row.source_refs:
                raise ValueError("Verified identity requires source references.")
            if row.instrument_type != "unknown" and not row.classification_evidence:
                raise ValueError("An explicit security classification requires evidence.")
            if row.security_form != "unknown" and not row.classification_evidence:
                raise ValueError("An explicit security form requires evidence.")
            if row.issuer_business_category != "unknown" and not row.issuer_classification_evidence:
                raise ValueError("An issuer business classification requires evidence.")
            if meta.source_kind == "listing_authority" and not row.source_refs:
                raise ValueError("A listing authority observation requires source references.")
            if row.symbol_aliases and not row.source_refs:
                raise ValueError("Security symbol aliases require source references.")
        payload = jsonable_encoder([row.model_dump() for row in rows])
        public_meta = jsonable_encoder(meta.model_dump())
        _public_reference([payload, public_meta])
        hashed_meta = {key: value for key, value in public_meta.items() if key != "retrieved_at"}
        fingerprint = hashlib.sha256(json.dumps({"records": payload, "provenance": hashed_meta}, sort_keys=True,
                                               allow_nan=False, separators=(",", ":")).encode()).hexdigest()
        now = utcnow()
        with self.session_factory.begin() as session:
            # Refreshes are rare administrative operations. Serialize their
            # identity upserts across workers without locking normal searches.
            if session.bind.dialect.name == "postgresql":
                session.execute(select(func.pg_advisory_xact_lock(6565001)))
            elif session.bind.dialect.name == "sqlite":
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            previous = session.scalar(select(SecurityRegistryRefresh).where(SecurityRegistryRefresh.content_hash == fingerprint))
            if previous:
                return {"refresh_id": previous.id, "registry_version": previous.content_hash,
                        "as_of": previous.as_of.isoformat(), "record_count": len(previous.records), "changed": False}
            source_count = session.scalar(select(func.count()).select_from(SecurityRegistryRefresh)
                                          .where(SecurityRegistryRefresh.source == meta.source))
            observation_count = session.scalar(select(func.count()).select_from(SecurityListingObservation))
            if source_count >= self.max_source_snapshots or observation_count + len(rows) > self.max_observations:
                raise ValueError("Registry history budget reached; review archival storage before publishing another snapshot. No evidence was deleted.")
            refresh = SecurityRegistryRefresh(content_hash=fingerprint, source=meta.source, as_of=meta.as_of,
                                              retrieved_at=meta.retrieved_at or now, complete_scope=meta.complete_scope,
                                              provenance=public_meta, records=payload)
            session.add(refresh)
            session.flush()
            issuers = session.scalars(select(SecurityIssuer)).all()
            by_issuer_key = {row.source_key: row for row in issuers}
            by_cik = {row.cik: row for row in issuers if row.cik}
            instruments = {row.source_key: row for row in session.scalars(select(SecurityInstrument))}
            listings = {row.source_key: row for row in session.scalars(select(SecurityListing))}
            by_listing_id = {row.id: row for row in listings.values()}
            by_instrument_id = {row.id: row for row in instruments.values()}
            by_issuer_id = {row.id: row for row in issuers}
            refresh_metadata = {row.id: row for row in session.scalars(select(SecurityRegistryRefresh)
                                .options(defer(SecurityRegistryRefresh.records)))}
            # Refresh memory follows source identities, not the entire retained
            # history. Exact historical records remain queryable separately.
            ranked_observations = select(SecurityListingObservation.id,
                func.row_number().over(partition_by=(SecurityListingObservation.source,
                                                     SecurityListingObservation.source_record_key),
                    order_by=(SecurityListingObservation.observed_on.desc(), SecurityListingObservation.retrieved_at.desc(),
                              SecurityListingObservation.id.desc())).label("source_rank")).subquery()
            observations = list(session.scalars(select(SecurityListingObservation)
                .join(ranked_observations, SecurityListingObservation.id == ranked_observations.c.id)
                .where(ranked_observations.c.source_rank == 1)))
            source_listing_map, source_observation_map, observations_by_listing = {}, {}, {}
            for observation in observations:
                source_listing_map[(observation.source, observation.source_record_key)] = observation.listing_id
                source_observation_map[(observation.source, observation.source_record_key)] = observation
                observations_by_listing.setdefault(observation.listing_id, []).append(observation)
            symbol_venues = {}
            for listing in listings.values():
                venue = exchange_mic(listing.exchange, listing.exchange_mic)
                symbol_venues.setdefault((listing.ticker, venue), set()).add(listing.id)
            for listing_id, value in session.execute(select(SecurityAlias.listing_id, SecurityAlias.normalized_value)
                                                     .where(SecurityAlias.kind == "symbol_alias")):
                listing = by_listing_id[listing_id]
                symbol_venues.setdefault((value, exchange_mic(listing.exchange, listing.exchange_mic)), set()).add(listing_id)
            # A sudden loss of most records is not a delisting signal. Refuse
            # publication and retain the last accepted source snapshot.
            if meta.source_kind == "listing_authority" and meta.complete_scope:
                previous_source = session.scalar(select(SecurityRegistryRefresh)
                    .where(SecurityRegistryRefresh.source == meta.source, SecurityRegistryRefresh.as_of <= meta.as_of,
                           SecurityRegistryRefresh.id != refresh.id)
                    .order_by(SecurityRegistryRefresh.as_of.desc(), SecurityRegistryRefresh.retrieved_at.desc()).limit(1))
                if previous_source and len(previous_source.records) >= 100 and len(rows) < len(previous_source.records) * .5:
                    raise ValueError("Directory quality quarantine: more than half of the previous source records disappeared.")
            instrument_dates = {}
            for listing in listings.values():
                instrument_dates[listing.instrument_id] = max(instrument_dates.get(listing.instrument_id, date.min), listing.as_of)
            changed_listings = []
            seen = {}
            for row in rows:
                record_key = row.source_record_key or source_key(meta.source, "record", row.cik, row.listing_key or row.instrument_key,
                                                                row.ticker, row.exchange_mic or row.exchange, str(row.valid_from or ""))
                linked_id = source_listing_map.get((meta.source, record_key))
                linked = by_listing_id.get(linked_id)
                previous_source = source_observation_map.get((meta.source, record_key))
                if previous_source and meta.as_of >= previous_source.observed_on:
                    prior = previous_source.record
                    old_class, new_class = prior.get("share_class"), row.share_class
                    old_form = prior.get("security_form", "unknown")
                    if old_form == "unknown" and prior.get("instrument_type") not in {None, "unknown", "reit", "financial_institution", "insurance"}:
                        old_form = prior["instrument_type"]
                    new_form = row.security_form
                    if new_form == "unknown" and row.instrument_type not in {"unknown", "reit", "financial_institution", "insurance"}:
                        new_form = row.instrument_type
                    if (old_class and new_class and normalized(old_class) != normalized(new_class)
                            or old_form != "unknown" and new_form != "unknown" and old_form != new_form):
                        raise ValueError("A mapped source identity cannot change its known share class or security form without explicit lifecycle reconciliation.")
                if meta.source_kind == "listing_authority":
                    venue = exchange_mic(row.exchange, row.exchange_mic)
                    candidate_ids = set()
                    if venue:
                        for symbol in [row.ticker, *row.symbol_aliases]:
                            candidate_ids.update(symbol_venues.get((symbol, venue), set()))
                    candidates = []
                    for candidate_id in candidate_ids:
                        candidate = by_listing_id[candidate_id]
                        candidate_instrument = by_instrument_id[candidate.instrument_id]
                        candidate_issuer = by_issuer_id.get(candidate_instrument.issuer_id)
                        # Name/CIK alone never links security classes. The
                        # independent SEC reference must also match an explicit
                        # source symbol and normalized listing venue exactly.
                        sec_proof = any(ref.get("provider") in {"sec", "sec-edgar"} for ref in candidate.source_refs)
                        if candidate_issuer and candidate_issuer.cik and sec_proof and (not row.cik or row.cik == candidate_issuer.cik):
                            candidates.append(candidate)
                    if len(candidates) > 1:
                        raise ValueError("Ambiguous cross-source security linkage; explicit source identity reconciliation is required.")
                    if linked and candidates and candidates[0].id != linked.id:
                        raise ValueError("A source security record conflicts with an existing issuer/security mapping.")
                    linked = linked or (candidates[0] if candidates else None)
                linked_instrument = by_instrument_id.get(linked.instrument_id) if linked else None
                linked_issuer = by_issuer_id.get(linked_instrument.issuer_id) if linked_instrument else None
                if linked_issuer and row.cik and linked_issuer.cik != row.cik:
                    raise ValueError("A source security record cannot be reassigned to another issuer.")
                ikey = source_key(meta.source, "issuer", row.issuer_key or row.cik or row.instrument_key or
                                  [row.ticker, row.exchange_mic or row.exchange])
                source_issuer = by_issuer_key.get(ikey)
                if source_issuer and row.cik and source_issuer.cik not in (None, row.cik):
                    raise ValueError("A source issuer key cannot be reassigned to another CIK.")
                issuer = linked_issuer or (by_cik.get(row.cik) if row.cik else None) or source_issuer
                if issuer is None:
                    issuer = SecurityIssuer(source_key=ikey, cik=row.cik, name=row.name,
                                            source_refs=row.source_refs, updated_at=now)
                    session.add(issuer)
                    # UUID defaults are assigned explicitly to avoid one flush per record.
                    issuer.id = identifier()
                    by_issuer_key[ikey] = issuer
                    by_issuer_id[issuer.id] = issuer
                    if row.cik:
                        by_cik[row.cik] = issuer
                elif row.cik and issuer.cik not in (None, row.cik):
                    raise ValueError("A source issuer key cannot be reassigned to another CIK.")
                elif row.cik and issuer.cik is None:
                    issuer.cik = row.cik
                    by_cik[row.cik] = issuer
                instrument_key = source_key(meta.source, "instrument", row.instrument_key or
                                            [row.cik or ikey, row.ticker, row.exchange_mic or row.exchange, row.share_class])
                instrument = linked_instrument or instruments.get(instrument_key)
                if instrument is None:
                    instrument = SecurityInstrument(id=identifier(), source_key=instrument_key, issuer_id=issuer.id,
                                                    instrument_type=row.instrument_type, share_class=row.share_class,
                                                    security_form=row.security_form if row.security_form != "unknown" else
                                                        row.instrument_type if row.instrument_type not in {"reit", "financial_institution", "insurance"} else "unknown",
                                                    classification_evidence=row.classification_evidence,
                                                    adr_metadata=row.adr_metadata, source_refs=row.source_refs, updated_at=now)
                    session.add(instrument)
                    instruments[instrument_key] = instrument
                    by_instrument_id[instrument.id] = instrument
                elif instrument.issuer_id != issuer.id:
                    raise ValueError("A source instrument key cannot be reassigned to another issuer.")
                # A symbol/venue change creates a new historical listing, even
                # when a source explicitly identifies the same instrument.
                lkey = source_key(meta.source, "listing", row.listing_key or instrument_key,
                                  row.ticker, row.exchange_mic or row.exchange, str(row.valid_from or ""))
                current = linked or listings.get(lkey)
                serialized = jsonable_encoder(row.model_dump())
                if lkey in seen and seen[lkey] != serialized:
                    raise ValueError("Conflicting records address the same listing in one snapshot.")
                if lkey in seen:
                    continue
                seen[lkey] = serialized
                old_observation = current is not None and current.as_of > meta.as_of
                if current is None:
                    current = SecurityListing(id=identifier(), source_key=lkey, instrument_id=instrument.id)
                    session.add(current)
                    listings[lkey] = current
                    by_listing_id[current.id] = current
                elif current.instrument_id != instrument.id:
                    raise ValueError("A listing cannot be reassigned to another instrument.")
                # Backfill only an actual legacy SEC snapshot clock. The new
                # exchange observation cannot stand in for old issuer proof.
                linkage = (current.verification or {}).get("issuer_linkage")
                legacy_refresh = refresh_metadata.get(current.refresh_id)
                sec_refs = [ref for ref in (current.source_refs or []) if ref.get("provider") in {"sec", "sec-edgar"}]
                if (not linkage and issuer.cik and legacy_refresh and legacy_refresh.source.startswith("sec-edgar")
                        and sec_refs and exchange_mic(current.exchange, current.exchange_mic)):
                    linkage = sec_issuer_linkage(ticker=current.ticker, venue=exchange_mic(current.exchange, current.exchange_mic),
                        cik=issuer.cik, issuer_id=issuer.id, observed_on=legacy_refresh.as_of.isoformat(),
                        registry_version=legacy_refresh.content_hash, source=legacy_refresh.source,
                        source_url=sec_refs[0].get("url"))
                explicit_sec_refs = [ref for ref in row.source_refs if ref.get("provider") in {"sec", "sec-edgar"}]
                if (meta.source_kind == "reference" and meta.source.startswith("sec-edgar") and explicit_sec_refs
                        and row.cik == issuer.cik and exchange_mic(row.exchange, row.exchange_mic)
                        and (not linkage or meta.as_of.isoformat() >= linkage["observed_on"])):
                    linkage = sec_issuer_linkage(ticker=row.ticker, venue=exchange_mic(row.exchange, row.exchange_mic),
                        cik=issuer.cik, issuer_id=issuer.id, observed_on=meta.as_of.isoformat(), registry_version=fingerprint,
                        source=meta.source, source_url=explicit_sec_refs[0].get("url"), record_hash=row.source_record_hash)
                if linkage:
                    current.verification = {**(current.verification or {}), "issuer_linkage": linkage}
                observation = SecurityListingObservation(id=identifier(), listing_id=current.id, refresh_id=refresh.id,
                    source=meta.source, source_record_key=record_key, source_kind=meta.source_kind,
                    observed_on=meta.as_of, published_at=meta.published_at, retrieved_at=meta.retrieved_at or now,
                    record_hash=row.source_record_hash or hashlib.sha256(json.dumps(serialized, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                    record=serialized, provenance=public_meta)
                session.add(observation)
                observations_by_listing.setdefault(current.id, []).append(observation)
                source_listing_map[(meta.source, record_key)] = current.id
                if old_observation:
                    project_listing(current, instrument, issuer, observations_by_listing[current.id])
                    continue  # Retain immutable old proof without rolling current fields backwards.
                previous_refs = current.source_refs or []
                for key in ("ticker", "name", "exchange", "exchange_mic", "listing_status", "identity_status",
                            "provider_symbols", "valid_from", "valid_to", "source_refs"):
                    if linked and linked.source_key != lkey and key in {"ticker", "name"}:
                        continue  # Preserve established canonical SEC symbol/company identity.
                    if key == "provider_symbols":
                        current.provider_symbols = {**(current.provider_symbols or {}), **row.provider_symbols}
                        continue
                    setattr(current, key, getattr(row, key))
                current.source_refs = list({json.dumps(ref, sort_keys=True): ref for ref in [*previous_refs, *row.source_refs]}.values())
                current.normalized_name = normalized(current.name)
                current.display_symbol = row.display_symbol or current.display_symbol or row.ticker
                current.security_description = row.security_description or current.security_description
                current.source_security_identifier = row.source_security_identifier or current.source_security_identifier
                current.as_of, current.refresh_id = meta.as_of, refresh.id
                if meta.as_of >= instrument_dates.get(instrument.id, date.min):
                    instrument.instrument_type = row.instrument_type
                    instrument.security_form = row.security_form if row.security_form != "unknown" else row.instrument_type if row.instrument_type not in {"reit", "financial_institution", "insurance"} else "unknown"
                    instrument.share_class = row.share_class
                    instrument.classification_evidence = row.classification_evidence
                    instrument.adr_metadata = row.adr_metadata
                    instrument.source_refs = row.source_refs
                    instrument.updated_at = now
                    instrument_dates[instrument.id] = meta.as_of
                if row.issuer_business_category != "unknown":
                    if issuer.business_category not in (None, "unknown", row.issuer_business_category):
                        raise ValueError("Conflicting issuer business classifications require explicit reconciliation.")
                    issuer.business_category, issuer.classification_evidence = row.issuer_business_category, row.issuer_classification_evidence
                project_listing(current, instrument, issuer, observations_by_listing[current.id])
                changed_listings.append((current, row))
            session.flush()
            changed_ids = [listing.id for listing, _ in changed_listings]
            if changed_ids:
                previous_aliases = {listing_id: {} for listing_id in changed_ids}
                for offset in range(0, len(changed_ids), 500):
                    for alias in session.scalars(select(SecurityAlias).where(SecurityAlias.listing_id.in_(changed_ids[offset:offset + 500]))):
                        previous_aliases[alias.listing_id][alias.normalized_value] = (alias.value, alias.kind, alias.source_refs)
                # Rebuild only aliases for changed listings. Original reference
                # observations remain immutable in the refresh snapshot.
                for offset in range(0, len(changed_ids), 500):
                    session.execute(delete(SecurityAlias).where(SecurityAlias.listing_id.in_(changed_ids[offset:offset + 500])))
                values = []
                for listing, row in changed_listings:
                    aliases = previous_aliases[listing.id]
                    def add_alias(value, kind, refs):
                        key = normalized(value)
                        previous = aliases.get(key)
                        if previous:
                            previous_value, previous_kind, previous_refs = previous
                            priority = {"ticker": 3, "symbol_alias": 2, "source_alias": 1, "name_token": 0}
                            if kind in {"ticker", "symbol_alias"} and previous_kind not in {"ticker", "symbol_alias"}:
                                # A name-only observation never becomes past
                                # security-symbol proof when a later source
                                # independently establishes this exact alias.
                                previous_refs = []
                            if priority[previous_kind] > priority[kind]:
                                # A matching company-name token is not new
                                # security-symbol evidence from this source.
                                if kind not in {"ticker", "symbol_alias"}:
                                    return
                                value, kind = previous_value, previous_kind
                            refs = list({json.dumps(ref, sort_keys=True): ref for ref in [*previous_refs, *refs]}.values())
                        aliases[key] = (value, kind, refs)
                    add_alias(row.ticker, "ticker" if row.ticker == listing.ticker else "symbol_alias", row.source_refs)
                    for value in row.aliases:
                        add_alias(value, "source_alias", row.source_refs)
                    for value in row.symbol_aliases:
                        if normalized(value) != normalized(row.ticker):
                            add_alias(value, "ticker" if value == listing.ticker else "symbol_alias", row.source_refs)
                    names = " ".join([row.name, *row.aliases])
                    for token in set(re.findall(r"[A-Z0-9]+", normalized(names))):
                        add_alias(token, "name_token", row.source_refs)
                    for alias, (value, kind, refs) in aliases.items():
                        values.append({"id": identifier(), "listing_id": listing.id,
                                       "value": value, "normalized_value": alias, "kind": kind,
                                       "source_refs": refs})
                for offset in range(0, len(values), 500):
                    session.execute(SecurityAlias.__table__.insert(), values[offset:offset + 500])
            current_keys = {item.source_record_key for group in observations_by_listing.values() for item in group
                            if item.source == meta.source and item.refresh_id == refresh.id}
            prior_keys = {item.source_record_key for item in observations if item.source == meta.source}
            omitted = sorted(prior_keys - current_keys) if meta.complete_scope else []
            return {"refresh_id": refresh.id, "registry_version": fingerprint, "as_of": meta.as_of.isoformat(),
                    "record_count": len(rows), "changed": True, "omitted_record_count": len(omitted),
                    "omitted_source_keys": omitted[:100], "omission_policy": "Preserved; absence is not delisting."}

    def listing_history(self, listing_id, limit=100, offset=0):
        """Bounded provenance inspection; original rows and clocks are retained."""
        with self.session_factory() as session:
            observations = session.scalars(select(SecurityListingObservation)
                .where(SecurityListingObservation.listing_id == str(listing_id))
                .order_by(SecurityListingObservation.observed_on.desc(), SecurityListingObservation.id)
                .offset(max(0, int(offset))).limit(min(100, max(1, int(limit))))).all()
            return [{"source": item.source, "source_record_key": item.source_record_key,
                     "observed_on": item.observed_on.isoformat(), "published_at": item.published_at,
                     "retrieved_at": as_utc(item.retrieved_at).isoformat(), "record_hash": item.record_hash,
                     "record": item.record, "provenance": item.provenance} for item in observations]

    def retention_plan(self, before, limit=100):
        """Never remove identity/history proof to meet a storage target.

        Operators get a bounded dry run. Referenced archives remain protected;
        no automatic deletion, background scheduling or cache cleanup occurs.
        """
        before = date.fromisoformat(str(before))
        with self.session_factory() as session:
            rows = session.scalars(select(SecurityRegistryRefresh)
                .options(defer(SecurityRegistryRefresh.records), defer(SecurityRegistryRefresh.provenance))
                .where(SecurityRegistryRefresh.as_of < before)
                .order_by(SecurityRegistryRefresh.as_of).limit(min(1000, max(1, int(limit))))).all()
            plan = []
            for row in rows:
                active = session.scalar(select(func.count()).select_from(SecurityListing).where(SecurityListing.refresh_id == row.id))
                history = session.scalar(select(func.count()).select_from(SecurityListingObservation).where(SecurityListingObservation.refresh_id == row.id))
                plan.append({"refresh_id": row.id, "source": row.source, "as_of": row.as_of.isoformat(),
                             "protected": bool(active or history), "current_listing_references": active,
                             "historical_observation_references": history})
            return {"dry_run": True, "before": before.isoformat(), "candidates": plan,
                    "deletion_performed": False, "policy": "Referenced identity and source-history archives must be preserved; operator archival review required."}

    @staticmethod
    def _statement():
        return (select(SecurityListing, SecurityInstrument, SecurityIssuer, SecurityRegistryRefresh)
                .options(defer(SecurityRegistryRefresh.records), defer(SecurityRegistryRefresh.provenance))
                .join(SecurityInstrument, SecurityListing.instrument_id == SecurityInstrument.id)
                .outerjoin(SecurityIssuer, SecurityInstrument.issuer_id == SecurityIssuer.id)
                .join(SecurityRegistryRefresh, SecurityListing.refresh_id == SecurityRegistryRefresh.id))

    @staticmethod
    def _identity(row, aliases=None, symbol_aliases=None):
        listing, instrument, issuer, refresh = row
        return {"issuer_id": issuer.id if issuer else None, "instrument_id": instrument.id, "listing_id": listing.id,
                "ticker": listing.ticker, "name": listing.name, "cik": issuer.cik if issuer else None,
                "exchange": listing.exchange, "exchange_mic": listing.exchange_mic,
                "instrument_type": instrument.instrument_type, "listing_status": listing.listing_status,
                "security_form": instrument.security_form,
                "issuer_business_category": issuer.business_category if issuer else "unknown",
                "issuer_classification_evidence": issuer.classification_evidence if issuer else {},
                "listing_verification": listing.verification or {"status": "reference_only", "confidence": "unverified"},
                "issuer_linkage": (listing.verification or {}).get("issuer_linkage") or {},
                "display_symbol": listing.display_symbol or listing.ticker,
                "security_description": listing.security_description,
                "source_security_identifier": listing.source_security_identifier,
                "identity_status": listing.identity_status, "share_class": instrument.share_class,
                "provider_symbols": listing.provider_symbols, "classification_evidence": instrument.classification_evidence,
                "adr_metadata": instrument.adr_metadata, "aliases": aliases or [],
                "symbol_aliases": symbol_aliases or [], "source_refs": listing.source_refs,
                "valid_from": listing.valid_from.isoformat() if listing.valid_from else None,
                "valid_to": listing.valid_to.isoformat() if listing.valid_to else None,
                "as_of": listing.as_of.isoformat(), "registry_as_of": listing.as_of.isoformat(),
                "registry_retrieved_at": as_utc(refresh.retrieved_at).isoformat(),
                "registry_version": refresh.content_hash}

    @staticmethod
    def _reassigned_symbols(session, tickers):
        if not tickers:
            return set()
        return set(session.scalars(select(SecurityListing.ticker)
                   .join(SecurityInstrument, SecurityListing.instrument_id == SecurityInstrument.id)
                   .where(SecurityListing.ticker.in_(tickers)).group_by(SecurityListing.ticker)
                   .having(func.count(func.distinct(SecurityInstrument.id)) > 1)).all())

    @staticmethod
    def _listing_aliases(session, listing_ids):
        grouped = {key: {"aliases": [], "symbol_aliases": []} for key in listing_ids}
        if not listing_ids:
            return grouped
        rows = session.execute(select(SecurityAlias.listing_id, SecurityAlias.value, SecurityAlias.kind)
                               .where(SecurityAlias.listing_id.in_(listing_ids),
                                      SecurityAlias.kind.in_(["source_alias", "symbol_alias"])))
        for listing_id, value, kind in rows:
            grouped[listing_id]["symbol_aliases" if kind == "symbol_alias" else "aliases"].append(value)
        return grouped

    def search(self, query, limit=10, offset=0, listing_status=None):
        if listing_status not in {None, "active", "inactive", "delisted", "suspended", "unknown"}:
            raise ValueError("Unknown listing status filter.")
        q = normalized(query)[:100]
        limit, offset = min(50, max(1, int(limit))), min(100000, max(0, int(offset)))
        with self.session_factory() as session:
            latest = session.execute(select(SecurityRegistryRefresh.as_of, SecurityRegistryRefresh.content_hash,
                                            SecurityRegistryRefresh.retrieved_at)
                                     .order_by(SecurityRegistryRefresh.as_of.desc(), SecurityRegistryRefresh.retrieved_at.desc()).limit(1)).first()
            if not q:
                matches = []
            else:
                alias_exact = exists(select(SecurityAlias.id).where(SecurityAlias.listing_id == SecurityListing.id,
                                                                   SecurityAlias.normalized_value == q,
                                                                   SecurityAlias.kind.in_(["ticker", "symbol_alias"])))
                words = re.findall(r"[A-Z0-9]+", q)
                # Find candidates through prefix indexes first. Avoid an
                # EXISTS-per-listing scan across the complete registry.
                candidates = [select(SecurityListing.id).where(SecurityListing.ticker.like(_prefix(q), escape="\\")),
                              select(SecurityAlias.listing_id).where(SecurityAlias.normalized_value == q,
                                                                     SecurityAlias.kind.in_(["ticker", "symbol_alias", "source_alias"]))]
                token_queries = [select(SecurityAlias.listing_id).where(SecurityAlias.normalized_value.like(_prefix(word), escape="\\"))
                                 for word in sorted(set(words))]
                if token_queries:
                    token_ids = token_queries[0] if len(token_queries) == 1 else intersect(*token_queries)
                    candidates.append(select(token_ids.subquery().c.listing_id))
                candidate_ids = union(*candidates)
                match = SecurityListing.id.in_(candidate_ids)
                rank = case((SecurityListing.ticker == q, 0), (alias_exact, 1),
                            (SecurityListing.ticker.like(_prefix(q), escape="\\"), 2), else_=3)
                active = case((SecurityListing.listing_status == "active", 0),
                              (SecurityListing.listing_status == "unknown", 1), else_=2)
                statement = self._statement().where(match)
                if listing_status:
                    statement = statement.where(SecurityListing.listing_status == listing_status)
                matches = session.execute(statement.order_by(rank, active, SecurityListing.ticker,
                                                                                 SecurityListing.id).offset(offset).limit(limit + 1)).all()
            reassigned = self._reassigned_symbols(session, [row[0].ticker for row in matches[:limit]])
            aliases = self._listing_aliases(session, [row[0].id for row in matches[:limit]])
            identities = [{**self._identity(row, **aliases[row[0].id]), "symbol_reassigned": row[0].ticker in reassigned}
                          for row in matches[:limit]]
            return {"results": identities, "status": "fresh" if latest else "partial", "warnings": [],
                    "limit": limit, "offset": offset, "has_more": len(matches) > limit,
                    "as_of": latest.as_of.isoformat() if latest else None,
                    "registry_as_of": latest.as_of.isoformat() if latest else None,
                    "registry_retrieved_at": as_utc(latest.retrieved_at).isoformat() if latest else None,
                    "registry_version": latest.content_hash if latest else None, "registry_empty": latest is None}

    def resolve(self, ticker, instrument_id=None, listing_id=None):
        q = normalized(ticker)
        with self.session_factory() as session:
            alias = exists(select(SecurityAlias.id).where(SecurityAlias.listing_id == SecurityListing.id,
                                                         SecurityAlias.normalized_value == q,
                                                         SecurityAlias.kind.in_(["ticker", "symbol_alias"])))
            statement = self._statement().where(or_(SecurityListing.ticker == q, alias))
            if instrument_id:
                statement = statement.where(SecurityInstrument.id == str(instrument_id))
            if listing_id:
                statement = statement.where(SecurityListing.id == str(listing_id))
            rows = session.execute(statement.order_by(SecurityListing.id)).all()
            if not rows:
                empty = session.scalar(select(SecurityListing.id).limit(1)) is None
                raise ApiError("registry_empty" if empty else "unknown_ticker",
                               "The security registry has no imported reference records." if empty else
                               "No security matches this ticker and selected identity.", 404)
            today = date.today()
            eligible = [row for row in rows if row[0].listing_status not in {"inactive", "delisted"}
                        and (row[0].valid_to is None or row[0].valid_to >= today)
                        and (row[0].valid_from is None or row[0].valid_from <= today)]
            if not eligible:
                raise ApiError("inactive_listing", "This dated listing is inactive; current financial analysis is unavailable.",
                               409, {"candidates": [self._identity(row) for row in rows]})
            identities = [self._identity(row) for row in eligible]
            if len(identities) != 1 or any(row["identity_status"] == "ambiguous" for row in identities):
                raise ApiError("identity_ambiguous", "Select an explicit exchange and instrument before financial analysis.",
                               409, {"candidates": identities})
            aliases = self._listing_aliases(session, [eligible[0][0].id])[eligible[0][0].id]
            result = self._identity(eligible[0], **aliases)
            result["symbol_reassigned"] = result["ticker"] in self._reassigned_symbols(session, [result["ticker"]])
            return result
