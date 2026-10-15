"""Independent forecast examples and conservative missing-evidence safeguards."""

from copy import deepcopy

import pytest

from app.valuation.forecasts import derive_forward_forecasts, revenue_path
from app.valuation.inputs import build_valuation_inputs
from test_valuation_historical_multiples import annual
from test_valuation_inputs_history import verified_company


@pytest.fixture
def example():
    periods = [annual(year) for year in range(2020, 2026)]
    inputs = {"currency": "USD", "financial_retrieved_at": "2026-03-01T00:00:00Z",
              "annual_periods": periods, "facts": deepcopy(periods[-1]["facts"]),
              "values": {"revenue": 1000, "trailing_eps": 10},
              "basis": {"share_basis_verified": True, "income_earnings_basis_verified": True}}
    evidence = {"historical_annual_periods": periods, "as_of_date": "2026-03-01",
                "splits": {"complete": True, "splits": []}}
    return inputs, evidence


def set_metric(period, field, value, *, scope_complete=True):
    period["metrics"][field] = value
    period["facts"][field] = {"value": value, "unit": "USD", "scope_complete": scope_complete,
                              "provenance": deepcopy(period["facts"]["revenue"]["provenance"])}


def test_revenue_path_independent_linear_fade_calculation():
    # Three years use growth10%,6%,2%; each year compounds prior revenue.
    assert revenue_path(100, 0.10, 0.02, 3) == pytest.approx([110, 116.6, 118.932])
    assert revenue_path(100, 0.10, 0.02, 3, fade=False) == pytest.approx([110, 121, 133.1])
    assert revenue_path(100, 0.10, 0.02, 1) == pytest.approx([110])


@pytest.mark.parametrize("arguments", [
    (100, 0.1, 0.02, 0), (100, 0.1, 0.02, 31), (100, 0.1, 0.02, True),
    (0, 0.1, 0.02, 5), (100, float("nan"), 0.02, 5), (100, -1, 0.02, 5),
    (100, 0.1, float("inf"), 5), (1e308, 1, 0.02, 5),
])
def test_invalid_revenue_path_inputs_are_rejected(arguments):
    with pytest.raises(ValueError):
        revenue_path(*arguments)


@pytest.mark.parametrize("ticker", ["AAPL", "MSFT", "NVDA", "ORCL"])
def test_no_new_evidence_preserves_every_phase4_default(ticker):
    fixture = verified_company(ticker)
    inputs = build_valuation_inputs(fixture["profile"], fixture["normalized"], fixture["retrieved_at"])
    before = deepcopy(inputs)
    assert derive_forward_forecasts(inputs, {})["assumptions"] == {}
    assert inputs == before


def test_forward_estimates_are_distinct_from_trailing_values_and_dated(example):
    result = derive_forward_forecasts(*example)
    assert result["assumptions"]["revenue_growth"]["value"] == 0
    assert result["assumptions"]["forward_eps"]["value"] == 10
    assert result["assumptions"]["forecast_revenue"]["value"] == 1000
    assert result["assumptions"]["forecast_ebitda"]["value"] == 220
    record = result["assumptions"]["forward_eps"]
    assert record["evidence_type"] == "estimate"
    assert record["computed_only"] is True
    assert record["dependency_fields"] == ["earnings_growth"]
    assert record["observation_date"] == "2026-02-04"


def test_user_growth_updates_forward_eps_ebitda_and_revenue_paths(example):
    inputs, evidence = example
    result = derive_forward_forecasts(inputs, evidence, overrides={"revenue_growth": 0.1, "earnings_growth": 0.15,
                                                                   "ebitda_margin": 0.3, "forecast_years": 3,
                                                                   "terminal_growth": 0.02})
    assert result["assumptions"]["forward_eps"]["value"] == pytest.approx(11.5)
    assert result["assumptions"]["forecast_revenue"]["value"] == pytest.approx(1100)
    assert result["assumptions"]["forecast_ebitda"]["value"] == pytest.approx(330)
    assert result["assumptions"]["projected_revenue"]["value"] == pytest.approx([1100, 1166, 1189.32])


def test_explicit_cleared_growth_does_not_reuse_a_default_forecast(example):
    result = derive_forward_forecasts(*example, overrides={"revenue_growth": None, "earnings_growth": None})
    assert "forecast_revenue" not in result["assumptions"]
    assert "projected_revenue" not in result["assumptions"]
    assert "forward_eps" not in result["assumptions"]


def test_growth_deceleration_uses_transparent_minimum_not_opaque_scores(example):
    inputs, evidence = example
    for year, period in enumerate(evidence["historical_annual_periods"]):
        value = 1000 * 1.2 ** year if year < 5 else 1000 * 1.2 ** 4 * 1.05
        set_metric(period, "revenue", value)
    inputs["values"]["revenue"] = evidence["historical_annual_periods"][-1]["metrics"]["revenue"]
    record = derive_forward_forecasts(inputs, evidence)["assumptions"]["revenue_growth"]
    assert record["value"] == pytest.approx(0.05)
    assert record["historical_analytics"]["latest_year_over_year"] == pytest.approx(0.05)
    assert record["lookback_years"] == 5
    assert "historical_growth_deceleration_rule" in record["policy_dependencies"]


def test_extraordinary_growth_is_bounded_and_clearly_policy_dependent(example):
    inputs, evidence = example
    for index, period in enumerate(evidence["historical_annual_periods"]):
        set_metric(period, "revenue", 1000 * 1.5 ** index)
    result = derive_forward_forecasts(inputs, evidence)
    record = result["assumptions"]["revenue_growth"]
    assert record["value"] == 0.2
    assert record["historical_analytics"]["raw_cagr"] == pytest.approx(0.5)
    assert "historical_forecast_growth_bounds" in record["policy_dependencies"]
    assert record["quality"] == "low"


def test_requested_lookback_requires_actual_window_without_fallback(example):
    inputs, evidence = example
    result = derive_forward_forecasts(inputs, evidence, overrides={"lookback_years": 10})
    assert "revenue_growth" not in result["assumptions"]
    assert "earnings_growth" not in result["assumptions"]
    three = derive_forward_forecasts(inputs, evidence, overrides={"lookback_years": 3.0})
    assert three["assumptions"]["revenue_growth"]["lookback_years"] == 3


def test_normalized_margins_use_median_of_three_compatible_observations(example):
    inputs, evidence = example
    for period, amount in zip(evidence["historical_annual_periods"][-3:], [100, 300, 200]):
        set_metric(period, "operating_income", amount)
    record = derive_forward_forecasts(inputs, evidence)["assumptions"]["operating_margin"]
    assert record["value"] == pytest.approx(0.2)
    assert record["financial_period"]["fiscal_years"] == [2023, 2024, 2025]
    assert "invented" in record["source_description"]


def test_missing_da_is_never_fabricated_from_margin_or_free_cash_flow(example):
    inputs, evidence = example
    for period in evidence["historical_annual_periods"]:
        period["facts"].pop("depreciation_and_amortization")
        period["metrics"].pop("depreciation_and_amortization")
    result = derive_forward_forecasts(inputs, evidence)
    assert "forecast_ebitda" not in result["assumptions"]
    assert "da_ratio" not in result["assumptions"]
    assert "fcff" not in result["assumptions"]
    assert "fcfe" not in result["assumptions"]


def test_eps_is_adjusted_using_verified_split_history_not_share_ratio_guess(example):
    inputs, evidence = example
    evidence["splits"]["splits"] = [{"date": "2023-07-01", "numerator": 10, "denominator": 1}]
    for period in evidence["historical_annual_periods"]:
        if period["fiscal_year"] >= 2023:
            set_metric(period, "net_income", 100)
            period["metrics"]["diluted_eps"] = period["facts"]["diluted_eps"]["value"] = 1
            period["metrics"]["weighted_average_diluted_shares"] = 100
            period["facts"]["weighted_average_diluted_shares"]["value"] = 100
    inputs["values"]["trailing_eps"] = 1
    result = derive_forward_forecasts(inputs, evidence)
    assert result["assumptions"]["earnings_growth"]["value"] == pytest.approx(0)
    assert result["assumptions"]["forward_eps"]["value"] == pytest.approx(1)
    evidence["splits"]["complete"] = False
    unavailable = derive_forward_forecasts(inputs, evidence)
    assert "earnings_growth" not in unavailable["assumptions"]
    assert "forward_eps" not in unavailable["assumptions"]


def test_incompatible_quoted_class_never_gets_issuer_eps_forecast(example):
    inputs, evidence = example
    inputs["basis"]["share_basis_verified"] = False
    inputs["basis"]["income_earnings_basis_verified"] = False
    result = derive_forward_forecasts(inputs, evidence)
    assert "forward_eps" not in result["assumptions"]
    assert "earnings_growth" not in result["assumptions"]
    assert "net_margin" not in result["assumptions"]


def test_complete_operating_working_capital_and_financing_have_independent_formulas(example):
    inputs, evidence = example
    working = [annual(year) for year in (2023, 2024, 2025)]
    for period, assets in zip(working, [300, 320, 340]):
        set_metric(period, "operating_current_assets", assets)
        set_metric(period, "operating_current_liabilities", 200)
    financing = [annual(year) for year in (2023, 2024, 2025)]
    for period, issued in zip(financing, [60, 80, 70]):
        set_metric(period, "debt_issuance", issued)
        set_metric(period, "debt_principal_repayments", 40)
    evidence["operating_working_capital_periods"] = working
    evidence["financing_periods"] = financing
    records = derive_forward_forecasts(inputs, evidence)["assumptions"]
    assert records["nwc_ratio"]["value"] == pytest.approx(0.12)
    assert records["change_nwc"]["value"] == 20
    assert records["net_borrowing"]["value"] == 30
    assert "constant_annual_net_borrowing" in records["net_borrowing"]["policy_dependencies"]


def test_unknown_operating_scope_and_debt_balance_changes_are_insufficient(example):
    inputs, evidence = example
    working = [annual(year) for year in (2023, 2024, 2025)]
    for period in working:
        set_metric(period, "operating_current_assets", 300, scope_complete=False)
        set_metric(period, "operating_current_liabilities", 200)
    evidence["operating_working_capital_periods"] = working
    evidence["financing_periods"] = working  # Totaldebt fact exists; actualflow records do not.
    records = derive_forward_forecasts(inputs, evidence)["assumptions"]
    assert "nwc_ratio" not in records
    assert "net_borrowing" not in records


def test_recent_collapsing_revenue_does_not_get_a_benign_bounded_forecast(example):
    inputs, evidence = example
    set_metric(evidence["historical_annual_periods"][-1], "revenue", 100)
    result = derive_forward_forecasts(inputs, evidence)
    assert "revenue_growth" not in result["assumptions"]
    assert result["forecast_quality"]["revenue_growth"]["reason"] == "recent_fundamental_collapse"


def test_nonfinite_or_invalid_fiscal_periods_remain_unavailable(example):
    inputs, evidence = example
    for period in evidence["historical_annual_periods"]:
        period["start_date"] = f"{period['fiscal_year']}-07-01"
    assert derive_forward_forecasts(inputs, evidence)["assumptions"] == {}


def test_forecasts_never_modify_original_periods_or_provider_snapshots(example):
    before = deepcopy(example)
    derive_forward_forecasts(*example, overrides={"revenue_growth": 0.15, "earnings_growth": 0.1})
    assert example == before
