"""Durable audit records for explicitly confirmed, atomic SEC imports."""
from datetime import datetime

from sqlalchemy import DateTime, JSON, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, utcnow


class FinancialImportBatch(Base):
    __tablename__ = "financial_import_batches"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    preview_digest: Mapped[str] = mapped_column(String(64), unique=True)
    source_inventory: Mapped[list] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    summary: Mapped[dict] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
