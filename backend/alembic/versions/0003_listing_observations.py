"""Add source-backed listing observations without changing financial ownership.

Revision ID: 0003_listing_observations
Revises: 0002_security_registry
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_listing_observations"
down_revision = "0002_security_registry"
branch_labels = None
depends_on = None


def json_type():
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade():
    op.add_column("security_issuers", sa.Column("business_category", sa.String(40), nullable=False, server_default="unknown"))
    op.add_column("security_issuers", sa.Column("classification_evidence", json_type(), nullable=False, server_default=sa.text("'{}'")))
    op.add_column("security_instruments", sa.Column("security_form", sa.String(40), nullable=False, server_default="unknown"))
    # A legacy bank/REIT label does not independently prove its quoted form.
    op.execute(sa.text("UPDATE security_instruments SET security_form = instrument_type WHERE instrument_type IN "
                       "('common_stock','foreign_ordinary','adr','etf','closed_end_fund','preferred','warrant','right','unit','other')"))
    for name, length in (("display_symbol", 40), ("security_description", 500), ("source_security_identifier", 100)):
        op.add_column("security_listings", sa.Column(name, sa.String(length)))
    op.add_column("security_listings", sa.Column("verification", json_type(), nullable=False, server_default=sa.text("'{}'")))
    op.create_table("security_listing_observations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("listing_id", sa.String(36), sa.ForeignKey("security_listings.id"), nullable=False),
        sa.Column("refresh_id", sa.String(36), sa.ForeignKey("security_registry_refreshes.id"), nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("source_record_key", sa.String(300), nullable=False),
        sa.Column("source_kind", sa.String(30), nullable=False),
        sa.Column("observed_on", sa.Date(), nullable=False),
        sa.Column("published_at", sa.String(100)),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_hash", sa.String(64), nullable=False),
        sa.Column("record", json_type(), nullable=False),
        sa.Column("provenance", json_type(), nullable=False),
        sa.UniqueConstraint("refresh_id", "source_record_key", name="uq_registry_observation_refresh_record"))
    op.create_index("ix_registry_observation_source_key", "security_listing_observations", ["source", "source_record_key"])
    op.create_index("ix_registry_observation_listing_date", "security_listing_observations", ["listing_id", "observed_on"])
    # Defaults serve the non-destructive backfill; ORM always supplies values.
    if op.get_bind().dialect.name == "postgresql":
        for table, columns in (("security_issuers", ("business_category", "classification_evidence")),
                               ("security_instruments", ("security_form",)), ("security_listings", ("verification",))):
            for column in columns:
                op.alter_column(table, column, server_default=None)


def downgrade():
    op.drop_table("security_listing_observations")
    for name in ("verification", "source_security_identifier", "security_description", "display_symbol"):
        op.drop_column("security_listings", name)
    op.drop_column("security_instruments", "security_form")
    op.drop_column("security_issuers", "classification_evidence")
    op.drop_column("security_issuers", "business_category")
