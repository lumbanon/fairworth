from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, JSON, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, utcnow

JsonType = JSON().with_variant(JSONB(), "postgresql")


class FinancialFact(Base):
    __tablename__ = "financial_facts"
    __table_args__ = (
        UniqueConstraint("company_id", "observation_key", name="uq_fact_observation"),
        Index("ix_facts_company_metric_period", "company_id", "normalized_metric", "period_end"),
        Index("ix_facts_accession", "accession_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    observation_key: Mapped[str] = mapped_column(String(64))
    concept: Mapped[str] = mapped_column(String(300))
    normalized_metric: Mapped[str | None] = mapped_column(String(100))
    reported_value: Mapped[float] = mapped_column(Numeric(30, 10))
    unit: Mapped[str] = mapped_column(String(50))
    fiscal_year: Mapped[int | None]
    fiscal_period: Mapped[str | None] = mapped_column(String(8))
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    filing_date: Mapped[date | None] = mapped_column(Date)
    accession_number: Mapped[str | None] = mapped_column(String(30))
    form_type: Mapped[str | None] = mapped_column(String(20))
    original_source: Mapped[dict] = mapped_column(JsonType)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FinancialSnapshot(Base):
    __tablename__ = "financial_snapshots"
    __table_args__ = (UniqueConstraint("company_id", "content_hash", name="uq_financial_snapshot_content"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    periods: Mapped[dict] = mapped_column(JsonType)
    normalized_data: Mapped[dict] = mapped_column(JsonType)
    warnings: Mapped[list] = mapped_column(JsonType)
    source_references: Mapped[list] = mapped_column(JsonType)
