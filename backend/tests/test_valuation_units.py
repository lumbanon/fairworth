"""Monetary/share conversion must be explicit and independently reproducible."""

from decimal import Decimal

import pytest

from app.valuation.units import (compatible_currencies, normalize_amount, normalize_shares,
                                 per_share, validate_model_units)
from app.valuation.validation import ValuationInputError


def test_monetary_scales_convert_using_decimal_without_intermediate_float_rounding():
    assert normalize_amount(123.45, "USD", "millions") == Decimal("123450000.00")
    assert normalize_amount(1.25, "EUR", "billions") == Decimal("1250000000.00")
    assert normalize_shares(12.5, "millions") == Decimal("12500000.0")


def test_money_and_shares_can_have_different_declared_presentation_scales():
    assert per_share(1000, 10, amount_currency="USD", result_currency="USD",
                     amount_scale="millions", share_scale="millions") == Decimal(100)
    assert per_share(1, 10, amount_currency="USD", result_currency="USD",
                     amount_scale="billions", share_scale="millions") == Decimal(100)
    assert per_share(1000000000, 10000000, amount_currency="USD", result_currency="USD") == Decimal(100)


def test_currency_is_preserved_and_no_foreign_exchange_conversion_is_invented():
    assert per_share(100, 10, amount_currency="EUR", result_currency="EUR") == Decimal(10)
    with pytest.raises(ValuationInputError):
        per_share(100, 10, amount_currency="EUR", result_currency="USD")
    with pytest.raises(ValuationInputError):
        compatible_currencies(None, "USD")


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), "100", True])
def test_invalid_or_missing_amounts_are_never_converted_to_zero(value):
    with pytest.raises(ValuationInputError):
        normalize_amount(value, "USD")


@pytest.mark.parametrize("value", [0, -1, None, float("nan")])
def test_denominator_must_be_positive_finite_and_present(value):
    with pytest.raises(ValuationInputError):
        normalize_shares(value)


def test_canonical_model_units_require_completed_boundary_conversion():
    validate_model_units({"currency": "EUR", "amount_unit": "EUR", "shares_unit": "shares"})
    for metadata in ({"currency": "EUR", "amount_unit": "USD"}, {"currency": "USD", "shares_unit": "millions"},
                     {"currency": "USD", "amount_scale": "billions"}, {"currency": "USD", "share_scale": "millions"}):
        with pytest.raises(ValuationInputError):
            validate_model_units(metadata)
