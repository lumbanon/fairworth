"""Actual retained public observations, distinct from synthetic model examples."""
import json
from pathlib import Path

import pytest

from app.valuation.forecasts import derive_forward_forecasts
from app.valuation.historical_multiples import derive_historical_multiples
from app.valuation.inputs import build_valuation_inputs


FIXTURES = Path(__file__).parent / "fixtures" / "valuation"


def examples():
    originals = json.loads((FIXTURES / "verified_provider_excerpts.json").read_text())["companies"]
    evidence = json.loads((FIXTURES / "automatic_evidence_excerpts.json").read_text())["companies"]
    return {ticker: (build_valuation_inputs(original["profile"], original["normalized"], original["retrieved_at"]),
                     evidence[ticker]["evidence"]) for ticker, original in originals.items()}


@pytest.mark.parametrize("ticker", ["AAPL", "MSFT", "NVDA", "ORCL"])
def test_retained_native_annuals_have_no_future_source_vintages(ticker):
    _, evidence = examples()[ticker]
    native = evidence["historical_annual_periods"]
    assert len(native) == 8
    assert len({p["fiscal_year"] for p in native}) == 8
    for period in native:
        assert all(source["filed"] <= period["publication_date"]
                   for fact in period["facts"].values() for source in fact.get("provenance", []))
        assert period["eps_split_basis_verified"] is (ticker != "ORCL")


@pytest.mark.parametrize("ticker,target,forward", [
    ("AAPL", 24.365144100054376, 7.4844189852700485),
    ("MSFT", 29.40123247853427, 21.072602133293124),
])
def test_actual_historical_medians_and_earnings_forecasts_are_reproducible(ticker, target, forward):
    inputs, evidence = examples()[ticker]
    multiple = derive_historical_multiples(inputs, evidence)
    forecast = derive_forward_forecasts(inputs, evidence)
    assert multiple["assumptions"]["target_pe"]["value"] == pytest.approx(target)
    assert multiple["statistics"]["pe"]["independent_fiscal_years"] == 5
    assert forecast["assumptions"]["forward_eps"]["value"] == pytest.approx(forward)
    assert multiple["assumptions"]["target_ev_ebitda"]["value"] is None
    assert multiple["assumptions"]["target_ev_revenue"]["value"] is None


def test_nvidia_original_eps_is_preserved_and_unstable_multiple_stays_missing():
    inputs, evidence = examples()["NVDA"]
    period = next(p for p in evidence["historical_annual_periods"] if p["fiscal_year"] == 2023)
    assert period["metrics"]["diluted_eps"] == 1.74
    assert next(event for event in evidence["splits"]["splits"] if event["date"] == "2024-06-10")["numerator"] == 10
    assert derive_historical_multiples(inputs, evidence)["assumptions"]["target_pe"]["value"] is None
    zero = evidence["observations"]["nonredeemable_preferred_equity"]
    assert zero["value"] == 0 and zero["state"] == "verified_zero"
    assert evidence["observations"]["preferred_equity"]["value"] is None


def test_microsoft_missing_complete_debt_and_aggregate_da_are_not_zero():
    _, evidence = examples()["MSFT"]
    obs = evidence["observations"]
    assert obs["debt"]["value"] is None
    assert obs["depreciation_and_amortization"]["value"] is None
    assert obs["depreciation_expense"]["value"] == 34_300_000_000
    assert obs["intangible_amortization_expense"]["value"] == 4_700_000_000
    assert evidence["provider_status"]["balance_sheet"] == "provider_subscription_required"


def test_oracle_restrictions_and_share_scope_remain_truthful():
    inputs, evidence = examples()["ORCL"]
    assert inputs["market"] is None
    assert evidence["historical_prices"]["prices"] == []
    assert evidence["splits"]["complete"] is False
    assert evidence["observations"]["current_shares"]["scope_verified"] is False
    assert evidence["observations"]["preferred_stock_stated_value"]["value"] == 4_954_000_000
    assert evidence["observations"]["preferred_equity"]["value"] is None
    assert derive_historical_multiples(inputs, evidence)["assumptions"]["target_pe"]["value"] is None
