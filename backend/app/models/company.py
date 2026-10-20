from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, utcnow


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (UniqueConstraint("ticker", "issuer_id", name="uq_companies_ticker_issuer"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    issuer_id: Mapped[str] = mapped_column(ForeignKey("security_issuers.id"), index=True)
    name: Mapped[str] = mapped_column(String(300))
    cik: Mapped[str] = mapped_column(String(10), index=True)
    exchange: Mapped[str | None] = mapped_column(String(100))
    sector: Mapped[str | None] = mapped_column(String(100))
    industry: Mapped[str | None] = mapped_column(String(250))
    currency: Mapped[str | None] = mapped_column(String(8))
    description: Mapped[str | None] = mapped_column(String)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
