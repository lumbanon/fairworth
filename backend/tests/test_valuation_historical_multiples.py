"""Independent hand calculations; synthetic facts are never production data."""

from copy import deepcopy
from datetime import date, timedelta

import pytest

from app.valuation.historical_multiples import derive_historical_multiples


def annual(year, eps=10):
    end = date(year, 12, 31)
    filed = end + timedelta(days=35)
    metrics = {"diluted_eps": eps, "net_income": eps * 10, "revenue": eps * 100,
               "shares_outstanding": 10, "weighted_average_diluted_shares": 10,
               "total_debt": 100, "cash_and_cash_equivalents": 20, "preferred_equity": 0,
               "minority_interest": 0, "other_nonoperating_assets": 0,
               "operating_income": 200, "depreciation_and_amortization": 20}
    facts = {}
    for key, value in metrics.items():
        unit = "USD/shares" if key == "diluted_eps" else "shares" if "shares" in key else "USD"
        facts[key] = {"value": value, "unit": unit, "source_type": "reported",
                      "split_basis_verified": True, "share_class_basis_verified": True,
                      "split_basis_date": filed.isoformat() if key == "diluted_eps" else end.isoformat(),
                      "scope_complete": True,
                      "value_state": "verified_zero" if value == 0 else "verified_positive",
                      "provenance": [{"accn": f"synthetic-{year}", "filed": filed.isoformat(),
                                      "source": "synthetic reported observation"}]}
    return {"fiscal_year": year, "fiscal_period": "FY", "start_date": f"{year}-01-01",
            "end_date": end.isoformat(), "currency": "USD", "metrics": metrics, "facts": facts}


@pytest.fixture
def example():
    periods = [annual(year) for year in range(2016, 2026)]
    prices = [{"date": (date(year, 12, 31) + timedelta(days=36)).isoformat(),
               "close": 30 + year - 2021, "currency": "USD", "provider": "synthetic market"}
              for year in range(2021, 2026)]
    inputs = {"currency": "USD", "financial_retrieved_at": "2026-02-15T00:00:00Z",
              "annual_periods": periods, "values": {"trailing_eps": 10, "revenue": 1000, "net_income": 100},
              "basis": {"share_basis_verified": True}, "market": None}
    evidence = {"as_of_date": "2026-02-15", "historical_annual_periods": periods,
                "historical_prices": {"provider": "synthetic market", "prices": prices,
                                      "adjustment_basis": "split_adjusted", "adjustment_date": "2026-02-15"},
                "splits": {"complete": True, "splits": []}}
    return inputs, evidence


def test_historical_forward_proxy_pe_and_trailing_statistic_are_distinct(example):
    inputs, evidence = example
    result = derive_historical_multiples(inputs, evidence)
    assert result["assumptions"]["target_pe"]["value"] == pytest.approx(3.2)
    assert result["statistics"]["pe"]["historical_trailing_median"] == pytest.approx(3.2)
    assert result["statistics"]["pe"]["independent_fiscal_years"] == 5
    assert result["assumptions"]["target_pe"]["evidence_type"] == "estimate"
    assert "not proof" in result["assumptions"]["target_pe"]["warnings"][0]["message"]
    assert result["assumptions"]["target_pe"]["dependency_fields"] == []


def test_forward_proxy_uses_growth_available_at_each_historical_price(example):
    inputs, evidence = example
    periods = [annual(year, 5 * 1.1 ** (year - 2016)) for year in range(2016, 2026)]
    evidence["historical_annual_periods"] = periods
    for period, price in zip(periods[-5:], evidence["historical_prices"]["prices"]):
        # A 20x trailing P/E and 10% as-of growth imply forward-proxy P/E20/1.1.
        price["close"] = period["metrics"]["diluted_eps"] * 20
    result = derive_historical_multiples(inputs, evidence)
    assert result["assumptions"]["target_pe"]["value"] == pytest.approx(20 / 1.1)
    assert result["statistics"]["pe"]["historical_trailing_median"] == pytest.approx(20)
    assert all(row["as_of_growth"]["used_growth"] == pytest.approx(0.1) for row in result["statistics"]["pe"]["observations"])


def test_no_lookahead_with_later_comparative_restatements(example):
    inputs, evidence = example
    # Later comparative filing publishes a different EPS; historical prices must
    # still use original EPS10, not the newly restated EPS100.
    restated = annual(2022, eps=100)
    for fact in restated["facts"].values():
        fact["provenance"][0]["filed"] = "2025-02-04"
    evidence["historical_annual_periods"].append(restated)
    result = derive_historical_multiples(inputs, evidence)
    row = next(row for row in result["statistics"]["pe"]["observations"] if row["fiscal_year"] == 2022)
    assert row["adjusted_trailing_eps"] == 10
    assert row["multiple"] == pytest.approx(3.1)


def test_same_day_filing_close_is_not_assumed_after_publication(example):
    inputs, evidence = example
    for row in evidence["historical_prices"]["prices"]:
        row["date"] = (date.fromisoformat(row["date"]) - timedelta(days=1)).isoformat()
    result = derive_historical_multiples(inputs, evidence)
    assert result["assumptions"]["target_pe"]["value"] is None
    assert all(row["reason"] == "missing_post_publication_price" for row in result["statistics"]["pe"]["excluded_observations"])


def test_split_adjusted_prices_and_original_eps_share_the_same_basis(example):
    inputs, evidence = example
    evidence["splits"]["splits"] = [{"date": "2026-02-10", "numerator": 10, "denominator": 1}]
    for row in evidence["historical_prices"]["prices"]:
        row["close"] /= 10  # FMP-style historical split-adjusted prices.
    result = derive_historical_multiples(inputs, evidence)
    assert result["assumptions"]["target_pe"]["value"] == pytest.approx(3.2)
    assert result["statistics"]["pe"]["observations"][0]["adjusted_trailing_eps"] == 1
    assert result["statistics"]["ev_revenue"]["observations"][0]["adjusted_period_end_common_shares"] == 100


@pytest.mark.parametrize("change", [
    lambda evidence: evidence["splits"].update(complete=False),
    lambda evidence: evidence["historical_prices"].update(adjustment_basis=None),
    lambda evidence: evidence["historical_prices"].update(adjustment_date=None),
    lambda evidence: evidence["historical_prices"].update(adjustment_date="2027-01-01"),
    lambda evidence: evidence["splits"].update(coverage_start="2025-01-01"),
    lambda evidence: evidence["splits"].update(coverage_end="2025-01-01"),
    lambda evidence: evidence["splits"].update(splits=[{"date": "2024-01-01", "numerator": float("inf"), "denominator": 1}]),
])
def test_unknown_or_invalid_adjustment_evidence_does_not_create_a_multiple(example, change):
    inputs, evidence = example
    change(evidence)
    assert derive_historical_multiples(inputs, evidence)["assumptions"]["target_pe"]["value"] is None


def test_unknown_eps_split_basis_does_not_become_an_estimate(example):
    inputs, evidence = example
    for period in evidence["historical_annual_periods"]:
        period["facts"]["diluted_eps"].pop("split_basis_verified")
    result = derive_historical_multiples(inputs, evidence)
    assert result["assumptions"]["target_pe"]["value"] is None


def test_future_earnings_adjustment_basis_cannot_precede_its_publication(example):
    inputs, evidence = example
    for period in evidence["historical_annual_periods"]:
        period["facts"]["diluted_eps"]["split_basis_date"] = "2026-02-15"
    assert derive_historical_multiples(inputs, evidence)["assumptions"]["target_pe"]["value"] is None


def test_unknown_reporting_currency_does_not_create_an_estimate(example):
    inputs, evidence = example
    inputs["currency"] = None
    for period in evidence["historical_annual_periods"]:
        period["currency"] = None
    assert all(item["value"] is None for item in derive_historical_multiples(inputs, evidence)["assumptions"].values())


def test_at_least_three_independent_fiscal_years_not_three_daily_prices(example):
    inputs, evidence = example
    price = evidence["historical_prices"]["prices"][-1]
    evidence["historical_prices"]["prices"] = [price, {**price, "date": "2026-02-06"}, {**price, "date": "2026-02-07"}]
    result = derive_historical_multiples(inputs, evidence)
    assert result["assumptions"]["target_pe"]["value"] is None
    assert result["statistics"]["pe"]["independent_fiscal_years"] == 1


def test_outliers_are_explicitly_reported_and_do_not_dominate_median(example):
    inputs, evidence = example
    evidence["historical_prices"]["prices"][-1]["close"] = 200
    result = derive_historical_multiples(inputs, evidence)
    assert result["assumptions"]["target_pe"]["value"] == pytest.approx(3.15)
    assert any(row["reason"] == "tukey_iqr_outlier" for row in result["statistics"]["pe"]["excluded_observations"])


def test_enterprise_multiple_matches_annual_cash_debt_and_common_share_basis(example):
    result = derive_historical_multiples(*example)
    # Median price32 x10actual periodendshares +debt100 -cash20 =EV400.
    assert result["assumptions"]["target_ev_revenue"]["value"] == pytest.approx(400 / 1000)
    assert result["assumptions"]["target_ev_ebitda"]["value"] == pytest.approx(400 / 220)
    assert "dated_period_end_share_proxy" in result["assumptions"]["target_ev_revenue"]["policy_dependencies"]


@pytest.mark.parametrize("field", ["total_debt", "cash_and_cash_equivalents", "preferred_equity", "minority_interest", "other_nonoperating_assets", "shares_outstanding"])
def test_missing_bridge_or_actual_common_shares_never_uses_weighted_average_proxy(example, field):
    inputs, evidence = example
    for period in evidence["historical_annual_periods"]:
        period["facts"].pop(field)
    result = derive_historical_multiples(inputs, evidence)
    assert result["assumptions"]["target_ev_revenue"]["value"] is None
    assert result["assumptions"]["target_ev_ebitda"]["value"] is None


@pytest.mark.parametrize("state", ["unknown", "unavailable", "user_supplied"])
def test_missing_claim_is_not_verified_zero_even_when_raw_numeric_is_zero(example, state):
    inputs, evidence = example
    for period in evidence["historical_annual_periods"]:
        period["facts"]["preferred_equity"]["value_state"] = state
    assert derive_historical_multiples(inputs, evidence)["assumptions"]["target_ev_revenue"]["value"] is None


def test_negative_current_earnings_cannot_use_positive_historical_pe(example):
    inputs, evidence = example
    inputs["values"]["trailing_eps"] = -1
    assert derive_historical_multiples(inputs, evidence)["assumptions"]["target_pe"]["value"] is None


def test_incompatible_share_class_remains_unavailable(example):
    inputs, evidence = example
    inputs["basis"]["share_basis_verified"] = False
    assert all(item["value"] is None for item in derive_historical_multiples(inputs, evidence)["assumptions"].values())


def test_large_profitability_regime_change_does_not_claim_history_still_relevant(example):
    inputs, evidence = example
    inputs["values"]["net_income"] = 800
    result = derive_historical_multiples(inputs, evidence)
    assert result["assumptions"]["target_pe"]["value"] is None
    assert result["assumptions"]["target_pe"]["warnings"][0]["code"] == "material_profitability_regime_change"


def test_no_mutation_and_nonfinite_prices_are_excluded(example):
    inputs, evidence = example
    evidence["historical_prices"]["prices"].append({"date": "2026-02-08", "close": float("nan"), "currency": "USD"})
    before = deepcopy((inputs, evidence))
    result = derive_historical_multiples(inputs, evidence)
    assert result["assumptions"]["target_pe"]["value"] == pytest.approx(3.2)
    assert inputs == before[0]
    assert evidence["historical_prices"]["prices"][:-1] == before[1]["historical_prices"]["prices"][:-1]


def test_short_fiscal_transition_and_conflicting_price_are_excluded(example):
    inputs, evidence = example
    evidence["historical_annual_periods"][-1]["start_date"] = "2025-07-01"
    row = evidence["historical_prices"]["prices"][0]
    evidence["historical_prices"]["prices"].append({**row, "close": row["close"] + 1})
    result = derive_historical_multiples(inputs, evidence)
    assert result["statistics"]["pe"]["independent_fiscal_years"] == 3
    assert any(row["reason"] == "conflicting_price_observations" for row in result["statistics"]["pe"]["excluded_observations"])
