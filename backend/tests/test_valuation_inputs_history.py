"""Boundary and history tests; synthetic unit examples are explicitly identified."""

import copy
import json
from pathlib import Path

import pytest

from app.services.normalization import METRIC_DEFINITIONS
from app.valuation.engine import calculate_valuation
from app.valuation.inputs import build_valuation_inputs, normalize_annual_period
from app.valuation.history import analyze_history, historical_cagr
from app.valuation.schemas import ValuationRequest


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "valuation" / "verified_provider_excerpts.json"


def verified_company(ticker):
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["companies"][ticker]


def synthetic_period(year=2024, metrics=None, currency="USD"):
    """Purely synthetic, consistently sourced calendar-year example."""
    values = metrics or {"revenue": 1000.0, "net_income": 100.0, "diluted_eps": 10.0,
                         "weighted_average_diluted_shares": 10.0, "shareholders_equity": 500.0}
    start, end = f"{year}-01-01", f"{year}-12-31"
    sources = {}
    for field, value in values.items():
        definition = METRIC_DEFINITIONS.get(field, (("SyntheticConcept",), currency, "duration"))
        unit = "shares" if "shares" in field else f"{currency}/shares" if field in ("basic_eps", "diluted_eps") else currency
        sources[field] = [{"value": value, "val": value, "unit": unit, "concept": definition[0][0],
                           "taxonomy": "us-gaap", "source": "synthetic-unit-example",
                           "start": None if definition[2] == "instant" else start, "end": end,
                           "filed": f"{year + 1}-02-15", "accn": f"synthetic-{year}", "fy": year, "fp": "FY", "form": "10-K"}]
    return {"fiscal_year": year, "fiscal_period": "FY", "start_date": start, "end_date": end,
            "currency": currency, "metrics": values, "provenance": sources, "warnings": []}


@pytest.mark.parametrize("ticker", ["AAPL", "MSFT", "NVDA", "ORCL"])
def test_verified_excerpts_retain_reported_values_and_metadata(ticker):
    fixture = verified_company(ticker)
    result = build_valuation_inputs(fixture["profile"], fixture["normalized"], fixture["retrieved_at"])
    original = fixture["normalized"]["annual"][-1]
    assert result["values"]["revenue"] == original["metrics"]["revenue"]
    assert result["facts"]["diluted_eps"]["value"] == original["metrics"]["diluted_eps"]
    assert result["facts"]["revenue"]["provenance"][0]["unit"] == "USD"
    assert result["facts"]["revenue"]["provenance"][0]["accn"]
    assert result["financial_retrieved_at"] == fixture["retrieved_at"]
    assert result["basis"]["current_shares_available"] is False
    assert all(result["values"][key] is None for key in ("net_borrowing", "change_nwc", "preferred_equity", "minority_interest", "other_nonoperating_assets", "fcff", "fcfe", "affo"))


def test_exact_known_provider_limitations_are_not_fabricated():
    msft = verified_company("MSFT")
    result = build_valuation_inputs(msft["profile"], msft["normalized"], msft["retrieved_at"])
    assert result["values"]["debt"] is None
    assert result["values"]["depreciation_and_amortization"] is None
    oracle = verified_company("ORCL")
    result = build_valuation_inputs(oracle["profile"], oracle["normalized"], oracle["retrieved_at"])
    assert result["market"] is None
    assert result["values"]["free_cash_flow"] < 0
    assert result["basis"]["share_basis_verified"] is False
    assert result["basis"]["income_earnings_basis_verified"] is False
    assert result["values"]["shares"] is None
    assert result["values"]["trailing_eps"] is None
    assert result["facts"]["diluted_eps"]["value"] == 5.83


def synthetic_share_class_inputs(ticker, multiple=None, verified=False):
    """Ticker syntax exercises identity checks; all financial values are synthetic."""
    profile = {"company": {"ticker": ticker, "name": "Synthetic share-basis example",
                            "has_multiple_share_classes": multiple,
                            "share_class_basis_verified": verified,
                            "is_bank": False, "is_reit": False}}
    return build_valuation_inputs(profile, {"currency": "USD", "annual": [synthetic_period()]})


def synthetic_pe_result(inputs, **assumptions):
    request = ValuationRequest(assumptions={"earnings_growth": 0.1, "target_pe": 20, **assumptions})
    return next(model for model in calculate_valuation(inputs, request)["scenarios"]["base"]["models"] if model["id"] == "pe")


@pytest.mark.parametrize("ticker", ["BRK-B", "BRK.B"])
@pytest.mark.parametrize("multiple", [None, False])
def test_unknown_share_class_does_not_reuse_issuer_eps_without_confirmation(ticker, multiple):
    inputs = synthetic_share_class_inputs(ticker, multiple=multiple)
    assert inputs["basis"]["share_basis_verified"] is False
    assert inputs["values"]["shares"] is None
    assert inputs["values"]["trailing_eps"] is None
    assert inputs["facts"]["diluted_eps"]["value"] == 10  # Original reported fact survives.
    blocked = synthetic_pe_result(inputs)
    assert blocked["status"] == "unavailable"
    assert "share_class_basis_unverified" in blocked["eligibility"]["reason_codes"]
    explicit_forecast = synthetic_pe_result(inputs, forward_eps=11)
    assert explicit_forecast["status"] == "valid"
    assert explicit_forecast["fair_value"] == pytest.approx(220)
    confirmed = synthetic_pe_result(inputs, share_basis_confirmed=True)
    assert confirmed["status"] == "valid"
    assert confirmed["fair_value"] == pytest.approx(220)


@pytest.mark.parametrize("ticker", ["BRK-B", "BRK.B"])
@pytest.mark.parametrize("multiple", [None, False, True])
def test_verified_share_class_can_use_compatible_reported_eps(ticker, multiple):
    inputs = synthetic_share_class_inputs(ticker, multiple=multiple, verified=True)
    assert inputs["basis"]["share_basis_verified"] is True
    result = synthetic_pe_result(inputs)
    assert result["status"] == "valid"
    assert result["fair_value"] == pytest.approx(220)


@pytest.mark.parametrize("multiple", [None, False])
def test_ordinary_single_class_ticker_preserves_historical_share_basis(multiple):
    inputs = synthetic_share_class_inputs("SYN", multiple=multiple)
    assert inputs["basis"]["share_basis_verified"] is True
    assert inputs["values"]["shares"] == 10
    result = synthetic_pe_result(inputs)
    assert result["status"] == "valid"
    assert result["fair_value"] == pytest.approx(220)


@pytest.mark.parametrize("change, code", [
    (lambda p: p["provenance"]["revenue"][0].update(unit="USD millions"), "incompatible_fact_units"),
    (lambda p: p["provenance"]["revenue"][0].update(start="2023-01-01"), "incompatible_fact_period"),
    (lambda p: p["provenance"]["revenue"][0].update(end="2024-09-30"), "incompatible_fact_period"),
    (lambda p: p["provenance"]["revenue"][0].update(value=2000), "reported_value_mismatch"),
    (lambda p: p["provenance"].update(revenue=[]), "missing_fact_provenance"),
    (lambda p: p["metrics"].update(revenue=float("inf")), "invalid_financial_value"),
    (lambda p: p["metrics"].update(revenue=True), "invalid_financial_value"),
])
def test_untrusted_facts_are_unavailable(change, code):
    period = synthetic_period()
    change(period)
    result = normalize_annual_period(period, "USD")
    assert result["metrics"]["revenue"] is None
    assert code in {item["code"] for item in result["facts"]["revenue"]["warnings"]}


def test_explicit_non_usd_reporting_currency_remains_unconverted():
    period = synthetic_period(currency="EUR")
    result = build_valuation_inputs({"company": {"ticker": "EURO"}}, {"currency": "EUR", "annual": [period]})
    assert result["values"]["revenue"] == 1000
    assert result["facts"]["diluted_eps"]["unit"] == "EUR/shares"
    assert result["currency"] == "EUR"


def test_ebitda_derived_only_from_valid_aligned_components():
    period = synthetic_period(metrics={"operating_income": 100, "depreciation_and_amortization": 25})
    result = build_valuation_inputs({"company": {}}, {"currency": "USD", "annual": [period]})
    assert result["values"]["ebitda"] == 125
    assert result["facts"]["ebitda"]["source_type"] == "derived"
    period["provenance"]["depreciation_and_amortization"][0]["start"] = "2024-04-01"
    result = build_valuation_inputs({"company": {}}, {"currency": "USD", "annual": [period]})
    assert result["values"]["ebitda"] is None


def test_signed_derived_fact_cannot_override_reported_components():
    fixture = verified_company("AAPL")
    fixture["normalized"]["annual"][-1]["metrics"]["free_cash_flow"] += 10000
    result = build_valuation_inputs(fixture["profile"], fixture["normalized"], fixture["retrieved_at"])
    assert result["values"]["free_cash_flow"] is None
    assert "derived_value_mismatch" in {item["code"] for item in result["facts"]["free_cash_flow"]["warnings"]}


def test_conflicting_latest_facts_and_invalid_source_numbers_are_safe():
    period = synthetic_period()
    inconsistent = copy.deepcopy(period)
    inconsistent["metrics"]["revenue"] = 1200
    inconsistent["provenance"]["revenue"][0].update(value=1200, val=1200)
    result = build_valuation_inputs({"company": {}}, {"currency": "USD", "annual": [period, inconsistent]})
    assert result["reporting_period"] is None
    period["provenance"]["revenue"][0]["value"] = float("inf")
    result = build_valuation_inputs({"company": {}}, {"currency": "USD", "annual": [period]})
    assert result["values"]["revenue"] is None
    json.dumps(result, allow_nan=False)


def test_historical_cagr_matches_independent_hand_calculation():
    periods = [synthetic_period(year=2020 + i, metrics={"revenue": 100 * 1.1 ** i}) for i in range(6)]
    assert historical_cagr(periods, "revenue", 3)["value"] == pytest.approx(0.1)
    assert historical_cagr(periods, "revenue", 5)["value"] == pytest.approx(0.1)
    assert historical_cagr(periods, "revenue", 10)["value"] is None


@pytest.mark.parametrize("amounts", [[-100, -110, -120, -130], [-100, 1, 5, 10], [100, 80, 0, 50], [100, 110, None, 130]])
def test_invalid_cagr_basis_reports_unavailable(amounts):
    periods = [synthetic_period(year=2020 + i, metrics={"revenue": value}) for i, value in enumerate(amounts)]
    assert historical_cagr(periods, "revenue", 3)["status"] == "unavailable"


def test_negative_growth_is_valid_when_all_observations_are_positive():
    periods = [synthetic_period(year=2020 + i, metrics={"revenue": 100 * 0.9 ** i}) for i in range(4)]
    assert historical_cagr(periods, "revenue", 3)["value"] == pytest.approx(-0.1)


def test_missing_fiscal_year_and_currency_changes_do_not_create_growth():
    periods = [synthetic_period(year=2020 + i, metrics={"revenue": 100 + i}) for i in range(5)]
    periods.pop(2)
    assert historical_cagr(periods, "revenue", 3)["value"] is None
    periods = [synthetic_period(year=2020 + i, metrics={"revenue": 100 + i}) for i in range(4)]
    periods[1]["currency"] = "EUR"
    assert historical_cagr(periods, "revenue", 3)["value"] is None


def test_fiscal_calendar_transition_is_not_assumed_comparable():
    periods = [synthetic_period(year=2020 + i, metrics={"revenue": 100 + i}) for i in range(4)]
    periods[-1].update(start_date="2023-04-01", end_date="2024-03-31")
    assert historical_cagr(periods, "revenue", 3)["value"] is None


def test_latest_unambiguous_restatement_selected_and_conflicts_excluded():
    periods = [normalize_annual_period(synthetic_period(year=2020 + i, metrics={"revenue": 100 * 1.1 ** i}), "USD") for i in range(4)]
    revised = copy.deepcopy(periods[-1])
    revised["metrics"]["revenue"] = 150
    revised["facts"]["revenue"]["provenance"][0]["filed"] = "2024-05-01"
    result = historical_cagr(periods + [revised], "revenue", 3)
    assert result["value"] == pytest.approx((150 / 100) ** (1 / 3) - 1)
    assert "restatement_selected" in {warning["code"] for warning in result["warnings"]}
    conflicting = copy.deepcopy(revised)
    conflicting["metrics"]["revenue"] = 160
    assert historical_cagr(periods + [revised, conflicting], "revenue", 3)["value"] is None


def test_average_equity_roe_and_negative_fcf_margin_are_reported():
    periods = [synthetic_period(year=2023, metrics={"revenue": 100, "shareholders_equity": 400, "net_income": 50}),
               synthetic_period(year=2024, metrics={"revenue": 200, "shareholders_equity": 600, "net_income": 100, "free_cash_flow": -20})]
    history = analyze_history(periods)
    assert history["margins"][-1]["return_on_equity"] == pytest.approx(0.2)
    assert history["margins"][-1]["free_cash_flow_margin"] == pytest.approx(-0.1)
    assert history["dividends"]["stable_per_share_dividend_verified"] is False
