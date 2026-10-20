"""Bind financial company buckets to a stable issuer without moving history.

Revision ID: 0004_financial_issuer_ownership
Revises: 0003_listing_observations

Ticker remains a compatibility lookup, not a global ownership key. Multiple
classes of one issuer retain their existing independent company buckets.
"""
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from alembic import op
import sqlalchemy as sa

revision = "0004_financial_issuer_ownership"
down_revision = "0003_listing_observations"
branch_labels = None
depends_on = None


def _cik(value):
    value = str(value or "")
    if not value.isascii() or not value.isdigit() or not 1 <= len(value) <= 10 or int(value) == 0:
        raise RuntimeError("Financial ownership migration aborted: a legacy issuer identifier is invalid.")
    return value.zfill(10)


def _sqlite_guard(connection):
    # SQLite batch ALTER rebuilds its parent table. With foreign keys enabled,
    # dropping that parent can cascade into facts even if every ID is retained.
    # Production PostgreSQL uses native ALTER and never rebuilds the table.
    if connection.dialect.name == "sqlite" and connection.exec_driver_sql("PRAGMA foreign_keys").scalar():
        if connection.execute(sa.text("SELECT count(*) FROM companies")).scalar():
            raise RuntimeError("Financial ownership migration aborted: populated SQLite with foreign keys enabled requires an explicit offline migration; no parent table was rebuilt.")


def upgrade():
    connection = op.get_bind()
    _sqlite_guard(connection)
    companies = list(connection.execute(sa.text("SELECT id, cik, name FROM companies")).mappings())
    issuer_table = sa.Table("security_issuers", sa.MetaData(), autoload_with=connection)
    by_cik = {}
    for row in connection.execute(sa.select(issuer_table.c.id, issuer_table.c.cik)):
        if row.cik:
            try:
                key = _cik(row.cik)
            except RuntimeError:
                continue
            by_cik.setdefault(key, []).append(row.id)
    assignments, additions = {}, {}
    for company in companies:
        cik = _cik(company["cik"])
        matches = by_cik.get(cik, [])
        if len(matches) > 1:
            raise RuntimeError("Financial ownership migration aborted: a legacy CIK has multiple registry issuers.")
        if matches:
            assignments[company["id"]] = matches[0]
        else:
            source_key = "legacy-financial-cik:" + cik
            issuer_id = str(uuid5(NAMESPACE_URL, source_key))
            additions.setdefault(cik, {"id": issuer_id, "source_key": source_key, "cik": cik,
                "name": company["name"], "source_refs": [], "business_category": "unknown",
                "classification_evidence": {}, "updated_at": datetime.now(timezone.utc)})
            assignments[company["id"]] = issuer_id
    # Every ownership mapping is checked before DDL or inserts. No original
    # company, fact, quote or snapshot row is rewritten, merged or removed.
    if additions:
        connection.execute(issuer_table.insert(), list(additions.values()))
    op.add_column("companies", sa.Column("issuer_id", sa.String(36), nullable=True))
    for company_id, issuer_id in assignments.items():
        connection.execute(sa.text("UPDATE companies SET issuer_id=:issuer WHERE id=:company"),
                           {"issuer": issuer_id, "company": company_id})
    with op.batch_alter_table("companies") as batch:
        batch.alter_column("issuer_id", existing_type=sa.String(36), nullable=False)
        batch.create_foreign_key("fk_companies_issuer_id", "security_issuers", ["issuer_id"], ["id"])
        batch.drop_index("ix_companies_ticker")
        batch.create_index("ix_companies_ticker", ["ticker"], unique=False)
        batch.create_index("ix_companies_issuer_id", ["issuer_id"], unique=False)
        batch.create_unique_constraint("uq_companies_ticker_issuer", ["ticker", "issuer_id"])


def downgrade():
    connection = op.get_bind()
    duplicate = connection.execute(sa.text("SELECT ticker FROM companies GROUP BY ticker HAVING count(*) > 1 LIMIT 1")).first()
    if duplicate:
        raise RuntimeError("Financial ownership downgrade aborted: reused tickers cannot fit the legacy unique-ticker schema. No financial rows were deleted or merged.")
    _sqlite_guard(connection)
    with op.batch_alter_table("companies") as batch:
        batch.drop_constraint("uq_companies_ticker_issuer", type_="unique")
        batch.drop_constraint("fk_companies_issuer_id", type_="foreignkey")
        batch.drop_index("ix_companies_issuer_id")
        batch.drop_index("ix_companies_ticker")
        batch.create_index("ix_companies_ticker", ["ticker"], unique=True)
        batch.drop_column("issuer_id")
    # Explicit legacy issuer references are retained. A rollback never deletes
    # registry observations or any financial source history.
