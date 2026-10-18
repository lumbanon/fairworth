import hashlib
import json
import math
from datetime import date, datetime

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select

from app.core.database import as_utc, utcnow
from app.core.exceptions import ApiError
from app.models import Company, FinancialFact, FinancialSnapshot, MarketSnapshot


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

    def save_company(self, profile):
        fields = {name: profile.get(name) for name in ("ticker", "name", "cik", "exchange", "sector", "industry", "description")}
        fields["currency"] = profile.get("currency")
        fields["updated_at"] = utcnow()
        with self.session_factory.begin() as session:
            insert_ignore(session, Company, [fields], ["ticker"])
            company = session.scalar(select(Company).where(Company.ticker == profile["ticker"]))
            if company.cik != profile.get("cik"):
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
            insert_ignore(session, MarketSnapshot, [snapshot], ["company_id", "content_hash"])

    def latest_snapshot(self, company_id):
        with self.session_factory() as session:
            return session.scalar(select(FinancialSnapshot).where(FinancialSnapshot.company_id == company_id)
                                  .order_by(FinancialSnapshot.snapshot_at.desc()).limit(1))
