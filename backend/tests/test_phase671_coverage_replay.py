"""Bounded coverage denominators, independent financial states and comparisons."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import replay_phase671_valuation_coverage as replay


def test_reported_financial_compatibility_does_not_require_a_target_multiple():
    checks = {key: {"status": "available"} for key in ("share_basis", "currency", "reporting_regime")}
    values = {"trailing_eps": 5, "target_pe": None, "earnings_growth": None}
    result = replay.financial_compatibility({}, values, [["trailing_eps", "target_pe", "earnings_growth"]], "pe", [], checks)
    assert result["compatible"] is True
    checks["share_basis"]["status"] = "unverified"
    assert replay.financial_compatibility({}, values, [["trailing_eps", "target_pe"]], "pe", [], checks)["compatible"] is False
    checks["share_basis"]["status"] = "available"
    assert replay.financial_compatibility({}, values, [["trailing_eps", "target_pe"]], "pe", ["trailing_eps"], checks)["compatible"] is False


def test_ranking_does_not_promise_sector_inapplicable_models():
    rows = [{"symbol": "BANK", "model_id": "fcff", "economic_appropriateness": "ineligible", "blockers": [{"code": "discount_rate_unavailable"}]},
            {"symbol": "OPERATING", "model_id": "fcff", "economic_appropriateness": "not_excluded", "blockers": [{"code": "discount_rate_unavailable", "fields": ["wacc"]}]}]
    ranked = replay.rank_blockers(rows)
    assert ranked[0]["affected_securities"] == ranked[0]["potentially_appropriate_security_model_pairs"] == 1
    assert "not promised" in ranked[0]["resolution"]


@pytest.fixture(scope="module")
def captured():
    return replay.capture("retained")


@pytest.fixture(scope="module")
def retained(captured):
    return replay.build_matrix("retained", "2026-10-20T15:25:12Z", captured=captured)


def test_real_retained_full_matrix_preserves_historical_regressions_and_scope(retained):
    assert retained["security_denominator"] == 30 and retained["model_pair_denominator"] == 330
    assert len({(row["symbol"], row["model_id"]) for row in retained["rows"]}) == 330
    assert retained["current_published_securities"] == 0
    assert retained["current_eligible_securities"] == 0
    assert retained["mocked_or_synthetic_results_included_in_real_coverage"] is False
    assert retained["historical_model_securities"] == 2
    values = {row["symbol"]: row["historical_replay_fair_value"] for row in retained["rows"] if row["historical_replay_model_eligible"]}
    assert values == {"AAPL": 214.2302568301956, "MSFT": 619.5604742486083}
    assert all(row["identity_scope"].startswith("deterministic fixture") for row in retained["rows"])
    assert all(row["model_contract"]["share_basis"] for row in retained["rows"])


def test_recomputed_status_is_not_replaced_by_old_historical_value(retained):
    row = next(row for row in retained["rows"] if row["symbol"] == "MSFT" and row["model_id"] == "pe")
    assert row["historical_replay_fair_value"] == 619.5604742486083
    assert row["calculated_fair_value"] is None and row["current_model_eligible"] is False
    assert row["result_type"] == "unavailable"


@pytest.mark.parametrize("change", ["population", "data_mode", "security_denominator", "model_pair_denominator", "source_clock", "pairs", "future"])
def test_comparison_refuses_cross_population_or_incomplete_history(retained, change):
    before = deepcopy(retained)
    if change == "pairs":
        before["rows"][0]["symbol"] = "WRONG"
    elif change == "future":
        before["as_of"] = "2026-10-22T00:00:00Z"
    else:
        before[change] = "mismatch"
    with pytest.raises(ValueError):
        replay.compare_reports(before, retained)


def test_clock_cannot_precede_source_acquisition():
    with pytest.raises(ValueError, match="Source evidence"):
        replay.build_matrix("retained", "2025-01-01T00:00:00Z", captured=({"as_of": "2026-01-01T00:00:00Z"}, {}))


def mocked_quote_inventory(response_symbol="MSFT"):
    clock = replay.instant("2026-10-21T07:00:00Z")
    return {"inventory": [{"provider": "fmp", "endpoint": "quote", "symbol": "MSFT", "status": "received",
        "payload": [{"symbol": response_symbol, "exchange": "NASDAQ", "timestamp": clock.timestamp(), "price": 123}],
        "retrieved_at": "2026-10-21T07:01:00Z", "url": "https://financialmodelingprep.com/stable/quote", "sha256": "0" * 64, "bytes": 1}]}


def test_mocked_local_quote_retains_missing_currency_and_original_financials(captured):
    original = deepcopy(captured)
    _, records = replay.apply_local_updates("retained", captured, mocked_quote_inventory(), replay.instant("2026-10-21T08:00:00Z"))
    inputs = records["MSFT"][0]
    assert inputs["market"]["price"] == 123 and inputs["market"]["currency"] is None
    assert inputs["market"]["price_timestamp"] == "2026-10-21T07:00:00+00:00"
    assert inputs["annual_periods"] == captured[1]["MSFT"][0]["annual_periods"]
    assert inputs["financial_retrieved_at"] == captured[1]["MSFT"][0]["financial_retrieved_at"]
    assert captured == original  # No mutable cache/fixture contamination.


def test_mocked_local_quote_cannot_cross_selected_security(captured):
    from app.core.exceptions import ApiError
    with pytest.raises(ApiError, match="Provider symbol"):
        replay.apply_local_updates("retained", captured, mocked_quote_inventory("NVDA"), replay.instant("2026-10-21T08:00:00Z"))
