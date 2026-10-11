from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import Envelope, FinancialPeriod, PeriodIdentity


class FinancialResponse(Envelope):
    ticker: str
    currency: str = "USD"
    period: Literal["annual", "quarterly"]
    periods: list[FinancialPeriod]
    source_references: list[dict] = Field(default_factory=list)
    retrieved_at: datetime


class MetricsResponse(Envelope):
    ticker: str
    periods: list[FinancialPeriod]
    retrieved_at: datetime


class DataStatusResponse(Envelope):
    ticker: str
    last_financial_update: datetime | None = None
    last_market_update: datetime | None = None
    available_periods: dict[str, list[PeriodIdentity]]
    missing_fields: list[str]
    provider_status: dict[str, dict[str, str]]
