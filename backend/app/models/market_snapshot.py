from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, utcnow


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"
    __table_args__ = (UniqueConstraint("company_id", "content_hash", name="uq_market_snapshot_content"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    price: Mapped[float | None] = mapped_column(Numeric(30, 10))
    currency: Mapped[str | None] = mapped_column(String(8))
    exchange: Mapped[str | None] = mapped_column(String(100))
    price_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    market_cap: Mapped[float | None] = mapped_column(Numeric(30, 4))
    shares_outstanding: Mapped[float | None] = mapped_column(Numeric(30, 4))
    provider: Mapped[str] = mapped_column(String(80))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    original_source: Mapped[dict] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
