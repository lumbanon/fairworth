"""Atomic reference imports and bounded indexed SQL discovery.

CIK identifies a registrant, never a security class. Source instrument keys may
link a rename only when the importer supplies that relationship explicitly.
"""
from __future__ import annotations

from datetime import date
import hashlib
import json
import re

from fastapi.encoders import jsonable_encoder
from sqlalchemy import case, delete, exists, func, intersect, or_, select, union
from sqlalchemy.orm import defer

from app.core.database import as_utc, utcnow
from app.core.exceptions import ApiError
from app.models.security_registry import (SecurityAlias, SecurityInstrument, SecurityIssuer,
                                           SecurityListing, SecurityRegistryRefresh, identifier)
from app.registry.schemas import RegistryProvenance, RegistryRecord


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
    def __init__(self, session_factory):
        self.session_factory = session_factory

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
            instrument_dates = {}
            for listing in listings.values():
                instrument_dates[listing.instrument_id] = max(instrument_dates.get(listing.instrument_id, date.min), listing.as_of)
            changed_listings = []
            seen = {}
            for row in rows:
                ikey = source_key(meta.source, "issuer", row.issuer_key or row.cik or row.instrument_key or
                                  [row.ticker, row.exchange_mic or row.exchange])
                source_issuer = by_issuer_key.get(ikey)
                if source_issuer and row.cik and source_issuer.cik not in (None, row.cik):
                    raise ValueError("A source issuer key cannot be reassigned to another CIK.")
                issuer = (by_cik.get(row.cik) if row.cik else None) or source_issuer
                if issuer is None:
                    issuer = SecurityIssuer(source_key=ikey, cik=row.cik, name=row.name,
                                            source_refs=row.source_refs, updated_at=now)
                    session.add(issuer)
                    # UUID defaults are assigned explicitly to avoid one flush per record.
                    issuer.id = identifier()
                    by_issuer_key[ikey] = issuer
                    if row.cik:
                        by_cik[row.cik] = issuer
                elif row.cik and issuer.cik not in (None, row.cik):
                    raise ValueError("A source issuer key cannot be reassigned to another CIK.")
                elif row.cik and issuer.cik is None:
                    issuer.cik = row.cik
                    by_cik[row.cik] = issuer
                instrument_key = source_key(meta.source, "instrument", row.instrument_key or
                                            [row.cik or ikey, row.ticker, row.exchange_mic or row.exchange, row.share_class])
                instrument = instruments.get(instrument_key)
                if instrument is None:
                    instrument = SecurityInstrument(id=identifier(), source_key=instrument_key, issuer_id=issuer.id,
                                                    instrument_type=row.instrument_type, share_class=row.share_class,
                                                    classification_evidence=row.classification_evidence,
                                                    adr_metadata=row.adr_metadata, source_refs=row.source_refs, updated_at=now)
                    session.add(instrument)
                    instruments[instrument_key] = instrument
                elif instrument.issuer_id != issuer.id:
                    raise ValueError("A source instrument key cannot be reassigned to another issuer.")
                # A symbol/venue change creates a new historical listing, even
                # when a source explicitly identifies the same instrument.
                lkey = source_key(meta.source, "listing", row.listing_key or instrument_key,
                                  row.ticker, row.exchange_mic or row.exchange, str(row.valid_from or ""))
                current = listings.get(lkey)
                serialized = jsonable_encoder(row.model_dump())
                if lkey in seen and seen[lkey] != serialized:
                    raise ValueError("Conflicting records address the same listing in one snapshot.")
                if lkey in seen:
                    continue
                seen[lkey] = serialized
                if current is not None and current.as_of > meta.as_of:
                    continue  # Append old observations; never roll current identity backwards.
                if current is None:
                    current = SecurityListing(id=identifier(), source_key=lkey, instrument_id=instrument.id)
                    session.add(current)
                    listings[lkey] = current
                elif current.instrument_id != instrument.id:
                    raise ValueError("A listing cannot be reassigned to another instrument.")
                for key in ("ticker", "name", "exchange", "exchange_mic", "listing_status", "identity_status",
                            "provider_symbols", "valid_from", "valid_to", "source_refs"):
                    setattr(current, key, getattr(row, key))
                current.normalized_name = normalized(row.name)
                current.as_of, current.refresh_id = meta.as_of, refresh.id
                if meta.as_of >= instrument_dates.get(instrument.id, date.min):
                    instrument.instrument_type = row.instrument_type
                    instrument.share_class = row.share_class
                    instrument.classification_evidence = row.classification_evidence
                    instrument.adr_metadata = row.adr_metadata
                    instrument.source_refs = row.source_refs
                    instrument.updated_at = now
                    instrument_dates[instrument.id] = meta.as_of
                changed_listings.append((current, row))
            session.flush()
            changed_ids = [listing.id for listing, _ in changed_listings]
            if changed_ids:
                # Rebuild only aliases for changed listings. Original reference
                # observations remain immutable in the refresh snapshot.
                for offset in range(0, len(changed_ids), 500):
                    session.execute(delete(SecurityAlias).where(SecurityAlias.listing_id.in_(changed_ids[offset:offset + 500])))
                values = []
                for listing, row in changed_listings:
                    aliases = {normalized(row.ticker): (row.ticker, "ticker")}
                    for value in row.aliases:
                        aliases.setdefault(normalized(value), (value, "source_alias"))
                    for value in row.symbol_aliases:
                        if normalized(value) != normalized(row.ticker):
                            aliases[normalized(value)] = (value, "symbol_alias")
                    names = " ".join([row.name, *row.aliases])
                    for token in set(re.findall(r"[A-Z0-9]+", normalized(names))):
                        aliases.setdefault(token, (token, "name_token"))
                    for alias, (value, kind) in aliases.items():
                        values.append({"id": identifier(), "listing_id": listing.id,
                                       "value": value, "normalized_value": alias, "kind": kind,
                                       "source_refs": row.source_refs})
                for offset in range(0, len(values), 500):
                    session.execute(SecurityAlias.__table__.insert(), values[offset:offset + 500])
            return {"refresh_id": refresh.id, "registry_version": fingerprint, "as_of": meta.as_of.isoformat(),
                    "record_count": len(rows), "changed": True}

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

    def search(self, query, limit=10, offset=0):
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
                matches = session.execute(self._statement().where(match).order_by(rank, active, SecurityListing.ticker,
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
