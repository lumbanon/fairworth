"""Independent assumption-framework examples and real availability regressions."""

import copy

import pytest

from app.valuation.assumptions import (
    AssumptionPolicy, estimate_cost_of_equity, estimate_wacc, generate_assumptions,
)
from app.valuation.inputs import build_valuation_inputs
from test_valuation_inputs_history import synthetic_period, verified_company


def company_inputs(ticker):
    fixture = verified_company(ticker)
    return build_valuation_inputs(fixture["profile"], fixture["normalized"], fixture["retrieved_at"])


def sourced(value, **kwargs):
    return {"value": value, "source": "synthetic mathematical test observation",
            "observation_date": "2024-12-31", **kwargs}


def test_benchmarks_are_explicit_policy_estimates_and_market_facts_stay_missing():
    result = generate_assumptions(company_inputs("AAPL"))
    assert result["values"]["cost_of_equity"] == 0.10
    assert result["metadata"]["cost_of_equity"]["source_type"] == "benchmark_assumption"
    assert "not a company fact" in result["metadata"]["cost_of_equity"]["source_description"]
    assert result["values"]["wacc"] is None
    assert result["values"]["risk_free_rate"] is None
    assert result["values"]["beta"] is None
    assert result["values"]["cost_of_debt"] is None
    assert all(result["values"][key] is None for key in ("target_pe", "target_ev_ebitda", "target_ev_revenue", "target_peg", "target_pb", "target_p_affo"))


def test_benchmark_policy_can_be_configured_or_required_return_disabled():
    result = generate_assumptions(company_inputs("AAPL"), policy=AssumptionPolicy(cost_of_equity=0.12, terminal_growth=0.015, forecast_years=7))
    assert result["values"]["cost_of_equity"] == 0.12
    assert result["values"]["terminal_growth"] == 0.015
    assert result["values"]["forecast_years"] == 7
    assert generate_assumptions(company_inputs("AAPL"), policy={"allow_benchmark_cost_of_equity": False})["values"]["cost_of_equity"] is None
    with pytest.raises(ValueError):
        generate_assumptions(company_inputs("AAPL"), policy={"forecast_years": 1000})


def test_forward_eps_forecast_is_disclosed_and_recomputed_from_growth():
    inputs = company_inputs("AAPL")
    result = generate_assumptions(inputs)
    # Independent five-year EPS CAGR from exact verified endpoints, then one year.
    periods = inputs["annual_periods"]
    expected_growth = (periods[-1]["metrics"]["diluted_eps"] / periods[0]["metrics"]["diluted_eps"]) ** (1 / 5) - 1
    assert result["values"]["earnings_growth"] == pytest.approx(expected_growth)
    assert result["metadata"]["forward_eps"]["value"] == pytest.approx(7.46 * (1 + expected_growth))
    assert result["metadata"]["forward_eps"]["source_type"] == "derived_estimate"
    assert result["values"]["forward_eps"] is None  # primitive recalculates dependent forecasts
    changed = generate_assumptions(inputs, {"earnings_growth": 0.15})
    assert changed["metadata"]["forward_eps"]["value"] == pytest.approx(7.46 * 1.15)
    assert changed["metadata"]["earnings_growth"]["overridden"] is True
    assert changed["metadata"]["earnings_growth"]["default_value"] == pytest.approx(expected_growth)
    explicit = generate_assumptions(inputs, {"forward_eps": 9.5})
    assert explicit["values"]["forward_eps"] == 9.5
    assert explicit["metadata"]["forward_eps"]["source_type"] == "user_assumption"
    assert explicit["metadata"]["forward_eps"]["default_value"] is None


def test_oracle_ambiguous_class_and_nvidia_split_basis_do_not_create_eps_forecasts():
    oracle = generate_assumptions(company_inputs("ORCL"))
    nvidia = generate_assumptions(company_inputs("NVDA"))
    assert oracle["values"]["earnings_growth"] is None
    assert oracle["metadata"]["forward_eps"]["value"] is None
    assert nvidia["values"]["earnings_growth"] is None
    assert nvidia["metadata"]["forward_eps"]["value"] is None
    assert "unverified_split_basis" in {warning["code"] for window in nvidia["history"]["growth"]["eps"].values() for warning in window["warnings"]}
    manual = generate_assumptions(company_inputs("ORCL"), {"forward_eps": 7, "target_pe": 20})
    assert manual["values"]["forward_eps"] == 7
    assert manual["values"]["target_pe"] == 20


def test_user_class_confirmation_unlocks_reported_eps_but_never_changes_income_basis():
    inputs = company_inputs("ORCL")
    result = generate_assumptions(inputs, {"share_basis_confirmed": True})
    assert result["values"]["earnings_growth"] == pytest.approx((5.83 / 4.55) ** (1 / 5) - 1)
    assert result["metadata"]["forward_eps"]["value"] == pytest.approx(5.83 * (1 + result["values"]["earnings_growth"]))
    assert "user_confirmed_share_basis" in {warning["code"] for warning in result["metadata"]["earnings_growth"]["warnings"]}
    assert result["values"]["return_on_equity"] is None
    assert inputs["basis"]["income_earnings_basis_verified"] is False
    assert inputs["values"]["trailing_eps"] is None  # facts/snapshot unchanged


def test_missing_working_capital_borrowing_claims_and_dividend_basis_stay_unavailable():
    for ticker in ("AAPL", "MSFT", "NVDA", "ORCL"):
        result = generate_assumptions(company_inputs(ticker))
        assert all(result["values"][key] is None for key in ("nwc_ratio", "net_borrowing", "change_nwc", "preferred_equity", "minority_interest", "other_nonoperating_assets", "dividend_per_share", "dividend_growth", "forward_affo_per_share"))
    result = generate_assumptions(company_inputs("MSFT"))
    assert result["values"]["da_ratio"] is None
    assert result["metadata"]["forecast_ebitda"]["value"] is None


def test_explicit_historical_lookback_changes_forecast_source_and_requires_window():
    inputs = company_inputs("AAPL")
    three = generate_assumptions(inputs, {"lookback_years": 3})
    assert "3-fiscal-year" in three["metadata"]["earnings_growth"]["source_description"]
    ten = generate_assumptions(inputs, {"lookback_years": 10})
    assert ten["values"]["earnings_growth"] is None
    assert ten["values"]["revenue_growth"] is None


def test_tax_rate_uses_same_period_reported_pretax_income_not_demo_constant():
    result = generate_assumptions(company_inputs("AAPL"))
    assert result["values"]["tax_rate"] == pytest.approx(20719000000 / 132729000000)
    assert result["metadata"]["tax_rate"]["source_type"] == "historical_estimate"
    assert generate_assumptions(company_inputs("ORCL"))["values"]["tax_rate"] is None


def test_growth_bound_is_disclosed_while_exact_historical_growth_is_preserved():
    periods = [synthetic_period(year=2020 + i, metrics={"revenue": 100 * 1.5 ** i}) for i in range(6)]
    inputs = build_valuation_inputs({"company": {}}, {"currency": "USD", "annual": periods})
    result = generate_assumptions(inputs)
    assert result["history"]["growth"]["revenue"]["5"]["value"] == pytest.approx(0.5)
    assert result["values"]["revenue_growth"] == 0.2
    assert "historical_growth_clamped" in {warning["code"] for warning in result["metadata"]["revenue_growth"]["warnings"]}


def test_justified_multiples_need_explicit_book_and_clean_surplus_confirmation():
    inputs = company_inputs("MSFT")
    result = generate_assumptions(inputs, {"book_value_meaningful": True, "clean_surplus_confirmed": True, "return_on_equity": 0.15, "cost_of_equity": 0.10, "terminal_growth": 0.02})
    # Independent stable growth formula: P/B=.13/.08; forward P/E=(1-.02/.15)/.08.
    assert result["values"]["target_pb"] == pytest.approx(1.625)
    assert result["values"]["target_pe"] == pytest.approx((1 - 0.02 / 0.15) / 0.08)
    assert result["metadata"]["target_pb"]["source_type"] == "derived_estimate"
    without_confirmation = generate_assumptions(inputs, {"return_on_equity": 0.15})
    assert without_confirmation["values"]["target_pb"] is None


@pytest.mark.parametrize("overrides", [{"earnings_growth": float("nan")}, {"target_pe": float("inf")}, {"target_pe": True}, {"projected_fcff": [1, float("nan")]}, {"projected_fcfe": list(range(31))}])
def test_invalid_assumptions_are_rejected(overrides):
    with pytest.raises(ValueError):
        generate_assumptions(company_inputs("AAPL"), overrides)


def test_assumptions_do_not_mutate_provider_facts():
    inputs = company_inputs("AAPL")
    previous = copy.deepcopy(inputs)
    generate_assumptions(inputs, {"forward_eps": 10, "shares": 100, "preferred_equity": 0})
    assert inputs == previous


def test_independent_sourced_capm_hand_calculation():
    result = estimate_cost_of_equity(sourced(0.04), sourced(1.2, method="synthetic OLS regression demonstration"), sourced(0.05))
    assert result["value"] == pytest.approx(0.04 + 1.2 * 0.05)
    assert result["source_type"] == "market_derived_estimate"


@pytest.mark.parametrize("change", [
    lambda records: records[0].pop("source"),
    lambda records: records[0].pop("observation_date"),
    lambda records: records[1].pop("estimation_method"),
    lambda records: records[0].update(observation_date="2200-01-01"),
    lambda records: records[1].update(value=float("inf")),
])
def test_capm_does_not_fabricate_missing_market_sources(change):
    records = [sourced(0.04), sourced(1.2, estimation_method="synthetic OLS demonstration"), sourced(0.05)]
    change(records)
    with pytest.raises(ValueError):
        estimate_cost_of_equity(*records)


def test_independent_wacc_market_value_hand_calculation_and_book_proxy_warning():
    debt_cost = sourced(0.05, method="synthetic bond-yield demonstration")
    equity = sourced(800, basis="market_value", currency="USD")
    debt = sourced(200, basis="market_value", currency="USD")
    result = estimate_wacc(0.10, debt_cost, 0.25, equity, debt)
    assert result["value"] == pytest.approx(0.8 * 0.1 + 0.2 * 0.05 * 0.75)
    debt["basis"] = "book_value"
    with pytest.raises(ValueError):
        estimate_wacc(0.10, debt_cost, 0.25, equity, debt)
    result = estimate_wacc(0.10, debt_cost, 0.25, equity, debt, allow_book_debt=True)
    assert any("book debt" in warning for warning in result["warnings"])


def test_wacc_rejects_book_equity_and_incompatible_currencies():
    debt_cost = sourced(0.05, method="synthetic demonstration")
    equity = sourced(800, basis="book_value", currency="USD")
    debt = sourced(200, basis="market_value", currency="USD")
    with pytest.raises(ValueError):
        estimate_wacc(0.1, debt_cost, 0.25, equity, debt)
    equity.update(basis="market_value", currency="EUR")
    with pytest.raises(ValueError):
        estimate_wacc(0.1, debt_cost, 0.25, equity, debt)
