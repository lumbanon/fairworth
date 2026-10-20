"""Add stable reference identities without touching financial history.

Revision ID: 0002_security_registry
Revises: 0001_financial_data
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_security_registry"
down_revision = "0001_financial_data"
branch_labels = None
depends_on = None


def json_type():
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade():
    op.create_table("security_registry_refreshes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("content_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("complete_scope", sa.Boolean(), nullable=False),
        sa.Column("provenance", json_type(), nullable=False), sa.Column("records", json_type(), nullable=False))
    op.create_index("ix_security_registry_refreshes_as_of", "security_registry_refreshes", ["as_of"])
    op.create_table("security_issuers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_key", sa.String(300), nullable=False, unique=True),
        sa.Column("cik", sa.String(10), unique=True), sa.Column("name", sa.String(300), nullable=False),
        sa.Column("source_refs", json_type(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("security_instruments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_key", sa.String(300), nullable=False, unique=True),
        sa.Column("issuer_id", sa.String(36), sa.ForeignKey("security_issuers.id")),
        sa.Column("instrument_type", sa.String(40), nullable=False), sa.Column("share_class", sa.String(100)),
        sa.Column("classification_evidence", json_type(), nullable=False), sa.Column("adr_metadata", json_type(), nullable=False),
        sa.Column("source_refs", json_type(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_security_instruments_issuer_id", "security_instruments", ["issuer_id"])
    op.create_table("security_listings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_key", sa.String(300), nullable=False, unique=True),
        sa.Column("instrument_id", sa.String(36), sa.ForeignKey("security_instruments.id"), nullable=False),
        sa.Column("ticker", sa.String(16), nullable=False), sa.Column("name", sa.String(300), nullable=False),
        sa.Column("normalized_name", sa.String(300), nullable=False), sa.Column("exchange", sa.String(100)),
        sa.Column("exchange_mic", sa.String(12)), sa.Column("listing_status", sa.String(20), nullable=False),
        sa.Column("identity_status", sa.String(30), nullable=False), sa.Column("provider_symbols", json_type(), nullable=False),
        sa.Column("valid_from", sa.Date()), sa.Column("valid_to", sa.Date()), sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("refresh_id", sa.String(36), sa.ForeignKey("security_registry_refreshes.id"), nullable=False),
        sa.Column("source_refs", json_type(), nullable=False))
    op.create_index("ix_security_listings_instrument_id", "security_listings", ["instrument_id"])
    op.create_index("ix_security_listings_refresh_id", "security_listings", ["refresh_id"])
    op.create_index("ix_registry_ticker_prefix", "security_listings", ["ticker"], postgresql_ops={"ticker": "varchar_pattern_ops"})
    op.create_index("ix_registry_name_prefix", "security_listings", ["normalized_name"], postgresql_ops={"normalized_name": "varchar_pattern_ops"})
    op.create_index("ix_registry_listing_status", "security_listings", ["listing_status", "exchange_mic"])
    op.create_table("security_aliases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("listing_id", sa.String(36), sa.ForeignKey("security_listings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("value", sa.String(300), nullable=False), sa.Column("normalized_value", sa.String(300), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False), sa.Column("source_refs", json_type(), nullable=False))
    op.create_index("ix_registry_alias_prefix", "security_aliases", ["normalized_value"],
                    postgresql_ops={"normalized_value": "varchar_pattern_ops"})
    op.create_index("ix_registry_alias_listing", "security_aliases", ["listing_id", "normalized_value"], unique=True)


def downgrade():
    # Existing companies, caches, facts and financial snapshots are untouched.
    for table in ("security_aliases", "security_listings", "security_instruments", "security_issuers", "security_registry_refreshes"):
        op.drop_table(table)
