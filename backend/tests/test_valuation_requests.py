"""Security and calculation bounds for valuation API requests."""
import math

import pytest
from pydantic import ValidationError

from app.valuation.schemas import ValuationRequest


@pytest.mark.parametrize("assumptions", [
    {"shares": 0}, {"shares": True}, {"forecast_years": 5.5}, {"forecast_years": 31},
    {"target_pe": 1000}, {"wacc": math.inf}, {"earnings_growth": math.nan},
    {"net_borrowing": "__import__('os')"}, {"url": "https://example.com"},
    {"share_basis_confirmed": 1}, {"projected_fcff": [1] * 31}, {"projected_fcfe": [False]},
])
def test_requests_reject_invalid_assumptions(assumptions):
    with pytest.raises(ValidationError):
        ValuationRequest(assumptions=assumptions)


def test_requests_preserve_explicit_zero_and_missing_components():
    request = ValuationRequest(assumptions={"minority_interest": 0, "net_borrowing": None, "projected_fcff": [-100, 200], "share_basis_confirmed": True})
    assert request.assumptions["minority_interest"] == 0
    assert request.assumptions["net_borrowing"] is None


@pytest.mark.parametrize("payload", [
    {"manual_market_price": {"value": -1, "currency": "USD"}},
    {"manual_market_price": {"value": math.inf, "currency": "USD"}},
    {"manual_market_price": {"value": 100, "currency": "usd"}},
    {"weights": {"reverse_dcf": 100}}, {"weights": {"pe": -1}},
    {"scenario_overrides": {"optimistic": {}}}, {"financials_url": "https://example.com"},
    {"sensitivity": {"model_id": "fcff", "x_parameter": "wacc", "y_parameter": "terminal_growth", "x_values": [0.1] * 12}},
    {"discount_rates": {"beta": {"value": 1, "source": "user estimate", "observation_date": "2025-01-01"}}},
])
def test_requests_reject_unbounded_or_unsupported_operations(payload):
    with pytest.raises(ValidationError):
        ValuationRequest(**payload)
