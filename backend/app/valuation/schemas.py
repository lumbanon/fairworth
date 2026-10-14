"""Bounded, explicit API contracts for transient valuation requests."""
from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any, Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from app.schemas.common import ApiModel

MODEL_IDS = ("fcff", "fcfe", "pe", "evEbitda", "evRevenue", "peg", "graham", "dividend", "residual", "pb", "affo")
ModelId = Literal["fcff", "fcfe", "pe", "evEbitda", "evRevenue", "peg", "graham", "dividend", "residual", "pb", "affo"]

GROWTH_FIELDS = {"revenue_growth", "earnings_growth", "cash_flow_growth", "dividend_growth"}
DISCOUNT_FIELDS = {"wacc", "cost_of_equity"}
MULTIPLE_FIELDS = {"target_pe", "target_ev_ebitda", "target_ev_revenue", "target_peg", "target_pb", "target_p_affo"}
FLAG_FIELDS = {"book_value_meaningful", "common_equity_basis_confirmed", "clean_surplus_confirmed", "stable_dividend_confirmed", "share_basis_confirmed", "affo_basis_confirmed", "is_bank", "is_reit", "growth_fade_to_terminal"}
AMOUNT_FIELDS = {"forward_eps", "forecast_revenue", "forecast_ebitda", "fcff", "fcfe", "net_borrowing", "change_nwc", "preferred_equity", "minority_interest", "other_nonoperating_assets", "debt", "cash", "book_equity", "affo", "forecast_affo", "dividend_per_share", "capex", "depreciation_and_amortization", "ebit", "net_income"}
RATIO_FIELDS = {"operating_margin", "net_margin", "ebitda_margin", "tax_rate", "capex_ratio", "da_ratio", "nwc_ratio", "return_on_equity", "terminal_roe", "payout_ratio", "reinvestment_rate"}
ARRAY_FIELDS = {"projected_fcff", "projected_fcfe", "projected_dividends"}
ASSUMPTION_KEYS = GROWTH_FIELDS | DISCOUNT_FIELDS | MULTIPLE_FIELDS | FLAG_FIELDS | AMOUNT_FIELDS | RATIO_FIELDS | ARRAY_FIELDS | {"terminal_growth", "forecast_years", "shares", "lookback_years"}


def validate_assumptions(values: dict) -> dict:
    for key, value in values.items():
        if key not in ASSUMPTION_KEYS:
            raise ValueError(f"Unknown assumption: {key}.")
        if value is None:
            continue
        if key in FLAG_FIELDS:
            if not isinstance(value, bool):
                raise ValueError(f"{key} must be a boolean confirmation.")
            continue
        if key in ARRAY_FIELDS:
            if not isinstance(value, list) or not 1 <= len(value) <= 30:
                raise ValueError(f"{key} must contain 1 to 30 annual values.")
            if any(isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item) or abs(item) > 1e18 for item in value):
                raise ValueError(f"{key} contains an invalid cash flow.")
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{key} must be a finite number.")
        if key == "forecast_years" and (not isinstance(value, int) or not 1 <= value <= 30):
            raise ValueError("forecast_years must be a whole number from 1 to 30.")
        if key == "lookback_years" and value not in (3, 5, 10):
            raise ValueError("lookback_years must be 3, 5, or 10.")
        if key in GROWTH_FIELDS and not -0.95 <= value <= 2:
            raise ValueError(f"{key} must be between -0.95 and 2, expressed as a fraction.")
        if key in DISCOUNT_FIELDS and not 0 < value <= 1:
            raise ValueError(f"{key} must be greater than zero and at most one.")
        if key == "terminal_growth" and not -0.1 <= value <= 0.1:
            raise ValueError("terminal_growth must be between -0.1 and 0.1.")
        if key in MULTIPLE_FIELDS and not 0 < value <= (10 if key == "target_peg" else 200):
            raise ValueError(f"{key} is outside the supported positive multiple range.")
        if key in RATIO_FIELDS and not (-1 <= value <= 1 if key in {"operating_margin", "net_margin", "nwc_ratio"} else -1 <= value <= 2 if key == "return_on_equity" else 0 <= value <= 3 if key in {"capex_ratio", "da_ratio"} else 0 <= value <= 2 if key == "terminal_roe" else 0 <= value <= 1):
            raise ValueError(f"{key} must be a supported fraction.")
        if key == "shares" and not 0 < value <= 1e15:
            raise ValueError("shares must be positive actual shares, not millions of shares.")
        if key in AMOUNT_FIELDS and abs(value) > 1e18:
            raise ValueError(f"{key} exceeds the supported financial amount range.")
        if key in {"debt", "cash", "preferred_equity", "minority_interest", "other_nonoperating_assets", "capex", "depreciation_and_amortization"} and value < 0:
            raise ValueError(f"{key} cannot be negative.")
    return values


class StrictModel(ApiModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ManualPrice(StrictModel):
    value: float = Field(gt=0, le=1e12, strict=True)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class SourcedRate(StrictModel):
    value: float = Field(ge=0, le=1, strict=True)
    source: str = Field(min_length=1, max_length=300)
    observation_date: date
    method: str | None = Field(default=None, min_length=1, max_length=300)


class SourcedDebtRate(SourcedRate):
    method: str = Field(min_length=1, max_length=300)


class SourcedBeta(StrictModel):
    value: float = Field(ge=0, le=5, strict=True)
    source: str = Field(min_length=1, max_length=300)
    observation_date: date
    method: str = Field(min_length=1, max_length=300)


class SourcedCapital(StrictModel):
    value: float = Field(ge=0, le=1e18, strict=True)
    source: str = Field(min_length=1, max_length=300)
    observation_date: date
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    basis: Literal["market_value", "book_value"] = "market_value"


class DiscountRateInputs(StrictModel):
    risk_free_rate: SourcedRate | None = None
    beta: SourcedBeta | None = None
    equity_risk_premium: SourcedRate | None = None
    cost_of_debt: SourcedDebtRate | None = None
    debt_market_value: SourcedCapital | None = None
    equity_market_value: SourcedCapital | None = None
    allow_book_debt: bool = False
    tax_rate: float | None = Field(default=None, ge=0, le=1)


class SensitivityRequest(StrictModel):
    model_id: ModelId
    x_parameter: str = Field(min_length=1, max_length=60)
    y_parameter: str = Field(min_length=1, max_length=60)
    x_values: list[float] | None = Field(default=None, min_length=1, max_length=11)
    y_values: list[float] | None = Field(default=None, min_length=1, max_length=11)

    @model_validator(mode="after")
    def valid_axes(self):
        if self.x_parameter == self.y_parameter:
            raise ValueError("Sensitivity axes must use distinct assumptions.")
        if self.x_parameter not in ASSUMPTION_KEYS or self.y_parameter not in ASSUMPTION_KEYS:
            raise ValueError("Unsupported sensitivity parameter.")
        for values in (self.x_values, self.y_values):
            if values and any(not math.isfinite(value) or abs(value) > 1e18 for value in values):
                raise ValueError("Sensitivity axes must use bounded finite numbers.")
        return self


class ValuationRequest(StrictModel):
    assumptions: dict[str, Any] = Field(default_factory=dict, max_length=70)
    scenario_overrides: dict[str, dict[str, Any]] = Field(default_factory=dict, max_length=3)
    weights: dict[ModelId, float] = Field(default_factory=dict, max_length=11)
    enabled_models: list[ModelId] | None = Field(default=None, max_length=11)
    manual_market_price: ManualPrice | None = None
    sensitivity: SensitivityRequest | None = None
    discount_rates: DiscountRateInputs | None = None

    @field_validator("assumptions")
    @classmethod
    def bounded_assumptions(cls, value):
        return validate_assumptions(value)

    @field_validator("scenario_overrides")
    @classmethod
    def bounded_scenarios(cls, value):
        if set(value) - {"bear", "base", "bull"}:
            raise ValueError("Scenarios must be bear, base, or bull.")
        for assumptions in value.values():
            validate_assumptions(assumptions)
        return value

    @field_validator("weights", mode="before")
    @classmethod
    def bounded_weights(cls, value):
        if any(isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(weight) or not 0 <= weight <= 10000 for weight in value.values()):
            raise ValueError("Weights must be finite nonnegative values at most 10000.")
        return value


class ModelResult(ApiModel):
    id: ModelId
    name: str
    short_name: str
    status: Literal["valid", "unavailable", "invalid_input"]
    fair_value: float | None = None
    upside: float | None = None
    margin_of_safety: float | None = None
    warnings: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    eligibility: dict[str, Any]


class ValuationSummary(ApiModel):
    fair_value: float | None = None
    upside: float | None = None
    margin_of_safety: float | None = None
    effective_weights: dict[str, float] = Field(default_factory=dict)
    count: int = 0
    warnings: list[str] = Field(default_factory=list)


class SensitivityCell(ApiModel):
    x_value: float
    fair_value: float | None = None
    status: Literal["valid", "unavailable", "invalid_input"]
    warnings: list[str] = Field(default_factory=list)


class SensitivityRow(ApiModel):
    y_value: float
    cells: list[SensitivityCell]


class SensitivityResponse(ApiModel):
    model_id: ModelId
    x_parameter: str
    y_parameter: str
    x_label: str
    y_label: str
    x_values: list[float]
    y_values: list[float]
    rows: list[SensitivityRow]
    unit: str
    warnings: list[str] = Field(default_factory=list)


class EligibilityResponse(ApiModel):
    company: dict[str, Any]
    engine_version: str
    models: list[dict[str, Any]]


class ScenarioResult(ApiModel):
    models: list[ModelResult]
    summary: ValuationSummary
    assumptions: dict[str, Any]
    confidence: dict[str, Any]


class ValuationResponse(ApiModel):
    engine_version: str
    calculated_at: datetime
    company: dict[str, Any]
    currency: str | None
    financials: dict[str, Any]
    defaults: dict[str, Any]
    scenarios: dict[str, ScenarioResult]
    suggested_weights: dict[str, float]
    configured_weights: dict[str, float]
    enabled_models: list[ModelId]
    market: dict[str, Any]
    reverse_dcf: dict[str, Any]
    sensitivity: dict[str, Any] | None = None
    warnings: list[dict[str, Any]]
    confidence: dict[str, Any]
