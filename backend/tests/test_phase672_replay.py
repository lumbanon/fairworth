"""Synthetic local response replay preserves scope, clocks and financial gates."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import replay_phase671_valuation_coverage as previous
from replay_phase672_valuation_coverage import apply_aapl_evidence


@pytest.fixture(scope="module")
def captured():
    return previous.capture("retained")


def synthetic_inventory(raw=None):
    profile = {"symbol": "AAPL", "cik": "0000320193", "currency": "USD", "exchange": "NASDAQ"}
    quote = {"symbol": "AAPL", "exchange": "NASDAQ", "price": 123, "timestamp": datetime.fromisoformat("2026-10-21T15:00:00+00:00").timestamp()}
    entries = [{"provider": "fmp", "endpoint": endpoint, "status": "received", "http_status": 200, "retrieved_at": "2026-10-21T15:00:01+00:00", "payload": [payload]}
               for endpoint, payload in (("profile", profile), ("quote", quote))]
    entries.append({"provider": "fmp", "endpoint": "splits", "status": "http_error", "http_status": 402, "retrieved_at": "2026-10-21T15:00:02+00:00", "payload": None})
    if raw:
        raw = deepcopy(raw); raw["cik"] = 320193
        entries.append({"provider": "sec", "endpoint": "companyfacts", "status": "received", "http_status": 200, "retrieved_at": "2026-10-21T15:00:03+00:00", "payload": raw})
    return {"inventory": entries}


def test_source_backed_mocked_quote_preserves_other_security_and_original_inputs(captured):
    original = deepcopy(captured)
    (_, records), assessment = apply_aapl_evidence(captured, synthetic_inventory(), previous.instant("2026-10-21T15:04:55Z"))
    assert assessment["quote_currency_status"] == "verified"
    assert records["AAPL"][0]["market"]["currency"] == "USD"
    assert records["AAPL"][0]["market"]["price"] == 123
    assert records["MSFT"] == captured[1]["MSFT"]
    assert captured == original


def test_new_facts_and_denied_splits_never_refresh_historical_complete_split_flag(captured, raw_facts):
    (_, records), assessment = apply_aapl_evidence(captured, synthetic_inventory(raw_facts), previous.instant("2026-10-21T15:04:55Z"))
    inputs = records["AAPL"][0]
    assert inputs["automatic_evidence"]["splits"]["complete"] is False
    assert inputs["automatic_evidence"]["splits"]["status"] == "provider_subscription_required"
    assert inputs["financial_source_status"]["currentness"]["status"] == "unverified"
    assert inputs["reporting_period"]["end_date"] == "2024-12-31"  # Original mock observation, not retrieval date.
    assert assessment["production_writes"] == 0


def test_new_aapl_bundle_never_applies_to_acquired_population_without_aapl():
    captured = ({"as_of": "2026-10-20T00:00:00Z"}, {"MSFT": ({"company": {"ticker": "MSFT"}}, {})})
    result, assessment = apply_aapl_evidence(captured, synthetic_inventory(), previous.instant("2026-10-21T15:04:55Z"))
    assert result == captured and assessment["applied"] is False
