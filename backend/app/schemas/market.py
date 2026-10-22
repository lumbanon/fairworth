from datetime import date, datetime

from pydantic import Field

from app.schemas.common import ApiModel, Envelope


class MarketQuote(Envelope):
    price: float | None = None
    currency: str | None = None
    exchange: str | None = None
    price_timestamp: datetime | None = None
    market_cap: float | None = None
    shares_outstanding: float | None = None
    provider: str
    retrieved_at: datetime
    original_currency: str | None = None
    currency_resolution: dict = Field(default_factory=dict)
    provider_capabilities: dict = Field(default_factory=dict)
    reporting_currency_compatibility: dict = Field(default_factory=dict)


class PriceObservation(ApiModel):
    date: date
    close: float
    open: float | None = None
    high: float | None = None
    low: float | None = None
    volume: float | None = None
    adjusted_close: float | None = None


class PricesResponse(Envelope):
    ticker: str
    identity: dict | None = None
    currency: str | None = None
    prices: list[PriceObservation]
    provider: str
    retrieved_at: datetime
    source_references: list[dict] = Field(default_factory=list)
