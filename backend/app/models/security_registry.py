"""Versioned reference identities; no financial facts or provider credentials."""
from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, JSON, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, utcnow


def identifier():
    return str(uuid4())


JsonType = JSON().with_variant(JSONB(), "postgresql")


class SecurityIssuer(Base):
    __tablename__ = "security_issuers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    source_key: Mapped[str] = mapped_column(String(300), unique=True)
    cik: Mapped[str | None] = mapped_column(String(10), unique=True)
    name: Mapped[str] = mapped_column(String(300))
    source_refs: Mapped[list] = mapped_column(JsonType, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SecurityInstrument(Base):
    __tablename__ = "security_instruments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    source_key: Mapped[str] = mapped_column(String(300), unique=True)
    issuer_id: Mapped[str | None] = mapped_column(ForeignKey("security_issuers.id"), index=True)
    issuer: Mapped[SecurityIssuer | None] = relationship()
    instrument_type: Mapped[str] = mapped_column(String(40), default="unknown")
    share_class: Mapped[str | None] = mapped_column(String(100))
    classification_evidence: Mapped[dict] = mapped_column(JsonType, default=dict)
    adr_metadata: Mapped[dict] = mapped_column(JsonType, default=dict)
    source_refs: Mapped[list] = mapped_column(JsonType, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SecurityListing(Base):
    __tablename__ = "security_listings"
    __table_args__ = (
        Index("ix_registry_ticker_prefix", "ticker", postgresql_ops={"ticker": "varchar_pattern_ops"}),
        Index("ix_registry_name_prefix", "normalized_name", postgresql_ops={"normalized_name": "varchar_pattern_ops"}),
        Index("ix_registry_listing_status", "listing_status", "exchange_mic"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    source_key: Mapped[str] = mapped_column(String(300), unique=True)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("security_instruments.id"), index=True)
    instrument: Mapped[SecurityInstrument] = relationship()
    ticker: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(300))
    normalized_name: Mapped[str] = mapped_column(String(300))
    exchange: Mapped[str | None] = mapped_column(String(100))
    exchange_mic: Mapped[str | None] = mapped_column(String(12))
    listing_status: Mapped[str] = mapped_column(String(20), default="unknown")
    identity_status: Mapped[str] = mapped_column(String(30), default="reference_only")
    provider_symbols: Mapped[dict] = mapped_column(JsonType, default=dict)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    as_of: Mapped[date] = mapped_column(Date)
    refresh_id: Mapped[str] = mapped_column(ForeignKey("security_registry_refreshes.id"), index=True)
    source_refs: Mapped[list] = mapped_column(JsonType, default=list)


class SecurityAlias(Base):
    __tablename__ = "security_aliases"
    __table_args__ = (
        Index("ix_registry_alias_prefix", "normalized_value", postgresql_ops={"normalized_value": "varchar_pattern_ops"}),
        Index("ix_registry_alias_listing", "listing_id", "normalized_value", unique=True),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    listing_id: Mapped[str] = mapped_column(ForeignKey("security_listings.id", ondelete="CASCADE"))
    value: Mapped[str] = mapped_column(String(300))
    normalized_value: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(30))
    source_refs: Mapped[list] = mapped_column(JsonType, default=list)


class SecurityRegistryRefresh(Base):
    __tablename__ = "security_registry_refreshes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True)
    source: Mapped[str] = mapped_column(String(100))
    as_of: Mapped[date] = mapped_column(Date, index=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    complete_scope: Mapped[bool] = mapped_column(Boolean, default=False)
    provenance: Mapped[dict] = mapped_column(JsonType)
    records: Mapped[list] = mapped_column(JsonType)
