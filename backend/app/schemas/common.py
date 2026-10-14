from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

DataStatus = Literal["fresh", "stale", "partial"]


class ApiModel(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)


class DataWarning(ApiModel):
    field: str
    code: str
    message: str


class PeriodIdentity(ApiModel):
    fiscal_year: int
    fiscal_period: str
    start_date: date | None = None
    end_date: date


class FinancialPeriod(PeriodIdentity):
    metrics: dict[str, float | None]
    provenance: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    warnings: list[DataWarning] = Field(default_factory=list)


class Envelope(ApiModel):
    status: DataStatus = "fresh"
    warnings: list[DataWarning] = Field(default_factory=list)


class ErrorDetail(ApiModel):
    code: str
    message: str
    details: list[dict[str, Any]] | dict[str, Any] | None = None


class ErrorResponse(ApiModel):
    error: ErrorDetail


class HealthResponse(ApiModel):
    status: Literal["ok", "unavailable"]
    database: Literal["ready", "unavailable"]
    phase: int = 4
    timestamp: datetime
