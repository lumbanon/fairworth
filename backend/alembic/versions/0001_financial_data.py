"""Provider-backed company data, original observations, snapshots, and cache.

Revision ID: 0001_financial_data
Revises: none
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_financial_data"
down_revision = None
branch_labels = None
depends_on = None


def json_type():
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade():
    op.create_table("companies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticker", sa.String(16), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("cik", sa.String(10), nullable=False),
        sa.Column("exchange", sa.String(100)), sa.Column("sector", sa.String(100)),
        sa.Column("industry", sa.String(250)), sa.Column("currency", sa.String(8)),
        sa.Column("description", sa.String()), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_companies_ticker", "companies", ["ticker"], unique=True)
    op.create_index("ix_companies_cik", "companies", ["cik"])
    op.create_table("financial_facts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("observation_key", sa.String(64), nullable=False),
        sa.Column("concept", sa.String(300), nullable=False), sa.Column("normalized_metric", sa.String(100)),
        sa.Column("reported_value", sa.Numeric(30, 10), nullable=False), sa.Column("unit", sa.String(50), nullable=False),
        sa.Column("fiscal_year", sa.Integer()), sa.Column("fiscal_period", sa.String(8)),
        sa.Column("period_start", sa.Date()), sa.Column("period_end", sa.Date()), sa.Column("filing_date", sa.Date()),
        sa.Column("accession_number", sa.String(30)), sa.Column("form_type", sa.String(20)),
        sa.Column("original_source", json_type(), nullable=False), sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "observation_key", name="uq_fact_observation"),
    )
    op.create_index("ix_financial_facts_company_id", "financial_facts", ["company_id"])
    op.create_index("ix_facts_company_metric_period", "financial_facts", ["company_id", "normalized_metric", "period_end"])
    op.create_index("ix_facts_accession", "financial_facts", ["accession_number"])
    op.create_table("financial_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False), sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("periods", json_type(), nullable=False), sa.Column("normalized_data", json_type(), nullable=False),
        sa.Column("warnings", json_type(), nullable=False), sa.Column("source_references", json_type(), nullable=False),
        sa.UniqueConstraint("company_id", "content_hash", name="uq_financial_snapshot_content"),
    )
    op.create_index("ix_financial_snapshots_company_id", "financial_snapshots", ["company_id"])
    op.create_index("ix_financial_snapshots_snapshot_at", "financial_snapshots", ["snapshot_at"])
    op.create_table("market_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False), sa.Column("price", sa.Numeric(30, 10)),
        sa.Column("currency", sa.String(8)), sa.Column("exchange", sa.String(100)), sa.Column("price_timestamp", sa.DateTime(timezone=True)),
        sa.Column("market_cap", sa.Numeric(30, 4)), sa.Column("shares_outstanding", sa.Numeric(30, 4)),
        sa.Column("provider", sa.String(80), nullable=False), sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("original_source", json_type(), nullable=False),
        sa.UniqueConstraint("company_id", "content_hash", name="uq_market_snapshot_content"),
    )
    op.create_index("ix_market_snapshots_company_id", "market_snapshots", ["company_id"])
    op.create_index("ix_market_snapshots_price_timestamp", "market_snapshots", ["price_timestamp"])
    op.create_table("cache_entries",
        sa.Column("key", sa.String(250), primary_key=True), sa.Column("payload", json_type(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("provider", sa.String(80), nullable=False),
    )
    op.create_index("ix_cache_entries_expires_at", "cache_entries", ["expires_at"])


def downgrade():
    for table in ("cache_entries", "market_snapshots", "financial_snapshots", "financial_facts", "companies"):
        op.drop_table(table)
