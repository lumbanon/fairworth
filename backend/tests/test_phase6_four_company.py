"""Actual dated four-company comparisons never force additional eligibility."""

from copy import deepcopy

import pytest

from app.valuation.engine import calculate_valuation
from phase6_company_helpers import COMPANIES, phase6_company_inputs, source_examples


@pytest.mark.parametrize("ticker,fair_value,count", [
    ("AAPL", 214.2302568301956, 1), ("MSFT", 619.5604742486083, 1),
    ("NVDA", None, 0), ("ORCL", None, 0),
])
def test_dated_additional_sources_preserve_defensible_model_coverage(ticker, fair_value, count):
    prepared, evidence, audit = phase6_company_inputs(ticker)
    preserved = deepcopy((prepared, evidence))
    result = calculate_valuation(prepared)
    base = result["scenarios"]["base"]
    assert len(base["models"]) == 11
    assert base["summary"]["count"] == count
    assert base["summary"]["fair_value"] == (pytest.approx(fair_value) if fair_value is not None else None)
    assert base["summary"]["classification"] == ("policy_based" if count else "unavailable")
    assert base["confidence"]["level"] == ("low" if count else "unavailable")
    assert {model["id"] for model in base["models"] if model["status"] == "valid"} == ({"pe"} if count else set())
    assert all(model["fair_value"] is None for model in base["models"] if model["status"] != "valid")
    assert audit["additional_period"]["end_date"] == prepared["reporting_period"]["end_date"]
    assert prepared["facts"]["stock_based_compensation"]["value"] is not None
    assert prepared["facts"]["stock_based_compensation"]["retrieved_at"] == audit["additional_financial_retrieved_at"]
    assert (prepared, evidence) == preserved
    if ticker in {"AAPL", "MSFT", "NVDA"}:
        assert prepared["values"]["debt"] is None
    else:
        assert prepared["values"]["debt"] == 129_541_000_000
        assert result["market"]["price"] is None


@pytest.mark.parametrize("ticker", COMPANIES)
def test_overlay_retains_every_original_nonnull_fact_except_explicit_debt_quarantine(ticker):
    sources, _, _ = source_examples()
    original = max(sources[ticker]["normalized"]["annual"], key=lambda period: period["end_date"])
    prepared, _, audit = phase6_company_inputs(ticker)
    for field, value in original["metrics"].items():
        if value is not None and field not in audit["quarantined_legacy_fields"]:
            assert prepared["facts"][field]["value"] == value
    original_quote = sources[ticker]["profile"].get("market")
    if original_quote:
        assert prepared["market"]["price"] == original_quote["price"]
        assert prepared["market"]["price_timestamp"] == original_quote["price_timestamp"]
    else:
        assert prepared["market"] is None
