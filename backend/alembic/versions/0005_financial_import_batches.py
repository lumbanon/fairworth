"""Retain immutable audit summaries for confirmed SEC imports.

Revision ID: 0005_financial_import_batches
Revises: 0004_financial_issuer_ownership
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_financial_import_batches"
down_revision = "0004_financial_issuer_ownership"
branch_labels = None
depends_on = None


def upgrade():
    payload = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table("financial_import_batches",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("preview_digest", sa.String(64), nullable=False, unique=True),
        sa.Column("source_inventory", payload, nullable=False),
        sa.Column("summary", payload, nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False))


def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM financial_import_batches")).scalar():
        raise RuntimeError("Import audit rollback refused: applied batches must retain their durable provenance.")
    # Only an empty audit table is removed; original financial history stays.
    op.drop_table("financial_import_batches")
