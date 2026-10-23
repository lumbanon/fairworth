import hashlib
import json
import math
from datetime import date, datetime
from uuid import NAMESPACE_URL, uuid5

from fastapi.encoders import jsonable_encoder
from sqlalchemy import inspect, or_, select

from app.core.database import as_utc, utcnow
from app.core.exceptions import ApiError
from app.models import CacheEntry, Company, FinancialFact, FinancialImportBatch, FinancialSnapshot, MarketSnapshot
from app.models.security_registry import SecurityIssuer
from app.providers.base import ProviderError, normalize_cik


def content_hash(value):
    return hashlib.sha256(json.dumps(jsonable_encoder(value), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def parse_instant(value):
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def insert_ignore(session, model, values, unique_fields):
    dialect = session.bind.dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        raise RuntimeError("Fairworth persistence requires PostgreSQL; SQLite is supported for tests.")
    session.execute(insert(model).values(values).on_conflict_do_nothing(index_elements=unique_fields))


class FinancialRepository:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def imported_dataset(self, issuer_id, cik):
        """Read an explicitly imported issuer snapshot without refreshing HTTP.

        Selected-security compatibility remains the valuation service's task.
        A later provider cache takes precedence; imports never rewrite it.
        Deployments without the optional migration retain their existing path.
        """
        if not issuer_id or not inspect(self.session_factory.kw["bind"]).has_table("financial_import_batches"):
            return None
        cik = normalize_cik(cik)
        with self.session_factory() as session:
            owners = session.scalars(select(Company).where(Company.issuer_id == issuer_id)).all()
            if len(owners) != 1 or normalize_cik(owners[0].cik) != cik:
                return None
            candidates = []
            for batch in session.scalars(select(FinancialImportBatch).order_by(FinancialImportBatch.applied_at.desc()).limit(1000)):
                for record in batch.summary.get("imported", []):
                    if (record.get("issuer_id") == issuer_id and record.get("company_id") == owners[0].id
                            and record.get("cik") == cik):
                        candidates.append((as_utc(parse_instant(record.get("retrieved_at"))), batch, record))
            candidates = [row for row in candidates if row[0] is not None]
            if not candidates:
                return None
            retrieved, batch, record = max(candidates, key=lambda row: (row[0], as_utc(row[1].applied_at)))
            caches = session.scalars(select(CacheEntry).where(or_(CacheEntry.key == f"sec:facts:{cik}",
                CacheEntry.key.startswith(f"sec:financials:{cik}:")))).all()
            if any(as_utc(row.retrieved_at) > retrieved for row in caches):
                return None
            original = session.get(CacheEntry, record.get("source_cache_key"))
            sources = [source for source in batch.source_inventory if source.get("cik") == cik
                and source.get("sha256") == record.get("source_sha256")]
            source = sources[0] if len(sources) == 1 else {}
            source_bound = (source.get("canonical_payload_sha256") == record.get("source_payload_hash")
                and source.get("source_url") == record.get("source_url")
                and source.get("source_url") == f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
                and as_utc(parse_instant(source.get("retrieved_at"))) == retrieved)
            if (not source_bound or original is None or not isinstance(original.payload, dict)
                    or content_hash(original.payload) != record.get("source_payload_hash")
                    or normalize_cik(original.payload.get("cik")) != cik
                    or as_utc(original.retrieved_at) != retrieved
                    or as_utc(original.expires_at) != as_utc(parse_instant(record.get("expires_at")))):
                raise ApiError("incompatible_financial_identity", "The imported SEC source failed its immutable audit binding.", 409)
            snapshot = session.get(FinancialSnapshot, record.get("snapshot_id"))
            from app.services.normalization import NORMALIZATION_VERSION, normalize_company_facts
            if (snapshot is None or snapshot.company_id != owners[0].id
                    or snapshot.content_hash != record.get("snapshot_hash")
                    or content_hash(snapshot.normalized_data) != snapshot.content_hash
                    or snapshot.normalized_data.get("normalization_version") != NORMALIZATION_VERSION
                    or record.get("normalization_version") != NORMALIZATION_VERSION
                    or batch.summary.get("normalization_version") != NORMALIZATION_VERSION
                    or content_hash(normalize_company_facts(original.payload, cik=cik)) != snapshot.content_hash):
                raise ApiError("incompatible_financial_identity", "The imported financial snapshot failed its immutable audit binding.", 409)
            archived = {}
            for listing_id, attachment in batch.summary.get("archived_security_proofs", {}).items():
                identity = attachment.get("identity") or {}
                expected_hash = content_hash({key: value for key, value in attachment.items() if key != "package_hash"})
                attachment_owners = [item for item in batch.summary.get("imported", [])
                    if item.get("issuer_id") == identity.get("issuer_id") and item.get("cik") == identity.get("cik")]
                attached_company = (session.get(Company, attachment_owners[0].get("company_id"))
                                    if len(attachment_owners) == 1 else None)
                if (attachment.get("package_hash") != expected_hash or identity.get("listing_id") != listing_id
                        or attached_company is None or attached_company.issuer_id != identity.get("issuer_id")
                        or normalize_cik(attached_company.cik) != identity.get("cik")):
                    raise ApiError("incompatible_financial_identity", "The archived selected-security attachment failed its immutable issuer and hash binding.", 409)
                from app.models.security_registry import SecurityInstrument, SecurityListing
                selected = session.get(SecurityListing, listing_id)
                instrument = session.get(SecurityInstrument, identity.get("instrument_id"))
                if (selected is None or instrument is None or selected.instrument_id != instrument.id
                        or instrument.issuer_id != identity.get("issuer_id") or selected.ticker != identity.get("ticker")
                        or selected.exchange_mic != identity.get("exchange_mic")):
                    raise ApiError("incompatible_financial_identity", "The archived selected-security attachment no longer matches its stable listing owner.", 409)
                if identity.get("issuer_id") == issuer_id and identity.get("cik") == cik:
                    archived[listing_id] = jsonable_encoder(attachment)
            return {"company_id": owners[0].id, "payload": jsonable_encoder(snapshot.normalized_data),
                "archived_security_proofs": archived,
                "retrieved_at": retrieved, "expires_at": as_utc(parse_instant(record.get("expires_at"))),
                "provenance": {"source_type": "approved_sec_financial_import", "import_batch_id": batch.id,
                    "imported_at": as_utc(batch.applied_at).isoformat(), "issuer_id": issuer_id,
                    "financial_owner_company_id": owners[0].id, "financial_owner_ticker": owners[0].ticker,
                    "cik": cik, "original_retrieved_at": retrieved.isoformat(),
                    "source_sha256": record["source_sha256"], "source_url": record["source_url"],
                    "snapshot_hash": snapshot.content_hash, "normalization_version": record["normalization_version"]}}

    def save_company(self, profile):
        fields = {name: profile.get(name) for name in ("ticker", "name", "cik", "exchange", "sector", "industry", "description")}
        fields["currency"] = profile.get("currency")
        fields["updated_at"] = utcnow()
        has_import_audit = inspect(self.session_factory.kw["bind"]).has_table("financial_import_batches")
        with self.session_factory.begin() as session:
            try:
                cik = normalize_cik(profile.get("cik"))
            except ProviderError:
                raise ApiError("incompatible_financial_identity", "Financial ownership requires a valid SEC issuer identifier.", 409) from None
            # Legacy registry rows may store an otherwise valid CIK without
            # ten-digit padding. Resolve all possible representations through
            # its unique index (at most ten keys), never create a second issuer
            # because its equivalent historical identifier has fewer zeros.
            digits = str(int(cik))
            cik_keys = [digits.zfill(width) for width in range(len(digits), 11)]
            matches = session.scalars(select(SecurityIssuer).where(SecurityIssuer.cik.in_(cik_keys))).all()
            if len(matches) > 1:
                raise ApiError("incompatible_financial_identity", "Multiple registry issuers represent this SEC identifier; ownership requires explicit reconciliation.", 409)
            explicit_issuer = profile.get("issuer_id")
            if explicit_issuer:
                issuer = matches[0] if matches else None
                if issuer is None or issuer.id != explicit_issuer:
                    raise ApiError("incompatible_financial_identity", "The selected stable issuer is not registered with this SEC identifier; historical data cannot be reassigned.", 409)
            else:
                # A bare symbol cannot authorize ownership by a different issuer.
                historical = session.scalars(select(Company).where(Company.ticker == profile["ticker"])).all()
                if any(normalize_cik(row.cik) != cik for row in historical):
                    raise ApiError("incompatible_financial_identity", "This ticker has historical data for another issuer. Select the registered issuer explicitly; historical observations cannot be reassigned.", 409)
                historical_owners = {row.issuer_id for row in historical}
                issuer = matches[0] if matches else None
                if len(historical_owners) > 1 or historical_owners and (issuer is None or issuer.id not in historical_owners):
                    raise ApiError("incompatible_financial_identity", "Historical company ownership conflicts with the registered SEC issuer; existing observations cannot be reassigned.", 409)
                if issuer is None:
                    source_key = "legacy-financial-cik:" + cik
                    insert_ignore(session, SecurityIssuer, [{"id": str(uuid5(NAMESPACE_URL, source_key)),
                        "source_key": source_key, "cik": cik, "name": profile["name"], "source_refs": [],
                        "business_category": "unknown", "classification_evidence": {}, "updated_at": utcnow()}], ["cik"])
                    issuer = session.scalar(select(SecurityIssuer).where(SecurityIssuer.cik == cik))
            if has_import_audit:
                imported_owners = set()
                batches = select(FinancialImportBatch.summary, FinancialImportBatch.source_inventory).execution_options(yield_per=50)
                for summary, sources in session.execute(batches):
                    for record in summary.get("imported", []):
                        if record.get("issuer_id") != issuer.id or record.get("cik") != cik:
                            continue
                        source_matches = [source for source in sources if source.get("cik") == cik
                                          and source.get("sha256") == record.get("source_sha256")]
                        if len(source_matches) != 1:
                            raise ApiError("incompatible_financial_identity", "The canonical imported financial owner has no exact source audit binding.", 409)
                        imported_owners.add(record.get("company_id"))
                if imported_owners:
                    owners = session.scalars(select(Company).where(Company.issuer_id == issuer.id)).all()
                    if (len(imported_owners) != 1 or len(owners) != 1 or owners[0].id not in imported_owners
                            or normalize_cik(owners[0].cik) != cik):
                        raise ApiError("incompatible_financial_identity", "The imported issuer has ambiguous financial ownership; existing history cannot be reassigned.", 409)
                    # An imported bucket belongs to the issuer. Visiting another
                    # listed class cannot create another owner or rewrite this
                    # frozen owner's descriptive or class-specific metadata.
                    return owners[0].id
            fields.update(cik=cik, issuer_id=issuer.id)
            insert_ignore(session, Company, [fields], ["ticker", "issuer_id"])
            company = session.scalar(select(Company).where(Company.ticker == profile["ticker"], Company.issuer_id == issuer.id))
            if normalize_cik(company.cik) != cik:
                raise ApiError("incompatible_financial_identity", "This ticker has historical data for another issuer. Its existing observations cannot be reassigned.", 409)
            for key, value in fields.items():
                if value is not None:
                    setattr(company, key, value)
            session.flush()
            return company.id

    def save_financials(self, company_id, observations, normalized):
        now = utcnow()
        rows = {}
        for observation in observations:
            value = observation.get("value", observation.get("val"))
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                continue
            original = jsonable_encoder(observation)
            identity = {key: value for key, value in original.items() if key not in {"metric", "retrieved_at"}}
            observation_key = content_hash(identity)
            rows[observation_key] = {
                "company_id": company_id, "observation_key": observation_key,
                "concept": observation.get("concept", "unknown"), "normalized_metric": observation.get("metric"),
                "reported_value": value, "unit": observation.get("unit", "unknown"),
                "fiscal_year": observation.get("fy"), "fiscal_period": observation.get("fp"),
                "period_start": parse_date(observation.get("start")), "period_end": parse_date(observation.get("end")),
                "filing_date": parse_date(observation.get("filed")), "accession_number": observation.get("accn"),
                "form_type": observation.get("form"), "original_source": original, "retrieved_at": now,
            }
        with self.session_factory.begin() as session:
            values = list(rows.values())
            for offset in range(0, len(values), 500):
                insert_ignore(session, FinancialFact, values[offset:offset + 500], ["company_id", "observation_key"])
            snapshot = {
                "company_id": company_id, "content_hash": content_hash(normalized), "snapshot_at": now,
                "periods": {kind: [period["end_date"] for period in normalized.get(kind, [])] for kind in ("annual", "quarterly")},
                "normalized_data": jsonable_encoder(normalized), "warnings": normalized.get("warnings", []),
                "source_references": normalized.get("source_references", []),
            }
            insert_ignore(session, FinancialSnapshot, [snapshot], ["company_id", "content_hash"])

    def save_market(self, company_id, quote):
        original = jsonable_encoder(quote)
        identity = {key: value for key, value in original.items() if key not in {"retrieved_at", "warnings", "status"}}
        snapshot = {key: quote.get(key) for key in ("price", "currency", "exchange", "market_cap", "shares_outstanding")}
        snapshot.update(company_id=company_id, content_hash=content_hash(identity),
                        price_timestamp=parse_instant(quote.get("price_timestamp")), provider=quote.get("provider", "unknown"),
                        retrieved_at=as_utc(parse_instant(quote.get("retrieved_at"))) or utcnow(), original_source=original)
        with self.session_factory.begin() as session:
            identity = quote.get("security_identity")
            if identity and not self._market_owner_matches(session.get(Company, company_id), identity):
                raise ApiError("incompatible_financial_identity", "A class-specific market observation cannot be saved under another selected security's financial owner.", 409)
            insert_ignore(session, MarketSnapshot, [snapshot], ["company_id", "content_hash"])

    @staticmethod
    def _market_owner_matches(company, identity):
        if company is None or company.ticker != identity.get("ticker"):
            return False
        try:
            if normalize_cik(company.cik) != normalize_cik(identity.get("cik")):
                return False
        except ProviderError:
            return False
        return identity.get("issuer_id") is None or identity["issuer_id"] == company.issuer_id

    def market_owner_matches(self, company_id, identity):
        with self.session_factory() as session:
            return self._market_owner_matches(session.get(Company, company_id), identity)

    def latest_snapshot(self, company_id):
        with self.session_factory() as session:
            return session.scalar(select(FinancialSnapshot).where(FinancialSnapshot.company_id == company_id)
                                  .order_by(FinancialSnapshot.snapshot_at.desc()).limit(1))
