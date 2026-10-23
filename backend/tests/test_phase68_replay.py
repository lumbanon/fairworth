"""Real financial, disposable import and simulated broker populations stay separate."""
import json
import hashlib
from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from replay_phase68_real_valuation import _private_ibkr, markdown, replay

CLOCK = "2026-10-22T06:51:30Z"


def test_real_sec_replay_does_not_claim_import_default_or_current_coverage():
    result = replay("retained-sec", CLOCK)
    assert result["intrinsic"]["value"] == pytest.approx(53.56)
    assert result["intrinsic"]["valuation_anchor_date"] == "2026-06-30"
    assert result["intrinsic"]["calculated_at"] == "2026-10-22T06:51:30+00:00"
    assert result["coverage"] == {"financial_statements_available": 1, "financial_data_imported_into_application": 0,
        "financial_data_imported_into_test_database": 0, "compatible_financial_evidence": 1,
        "automatic_default_model_eligible": 0, "user_assisted_model_eligible": 1,
        "historical_real_data_intrinsic_estimate": 1, "current_intrinsic_under_reviewed_policy": 0,
        "compatible_current_market_comparison": 0, "two_corroborating_model_families": 0}
    assert result["application_writes"] == result["live_provider_requests"] == 0
    assert "53.56" in markdown(result)


def test_real_excerpt_test_import_is_idempotent_and_never_application_import():
    result = replay("test-import", CLOCK)
    assert result["coverage"]["financial_data_imported_into_test_database"] == 1
    assert result["coverage"]["financial_data_imported_into_application"] == 0
    assert result["test_database_import"]["row_changes"]["financial_facts"] == 12
    assert result["test_database_import"]["repeat_already_applied"] is True
    assert result["intrinsic"]["value"] == pytest.approx(53.56)
    assert result["published_api_response"]["status_code"] == 200


def test_mock_ibkr_is_a_separate_private_population_not_a_live_valuation():
    result = replay("mock-ibkr", CLOCK)
    private = result["private_market_population"]
    assert private["data_mode"] == "simulated_ibkr"
    assert private["observation"]["market_data_type"] == "delayed"
    assert result["coverage"]["compatible_current_market_comparison"] == 0
    assert result["market_comparison"]["status"] == "unavailable"
    assert private["comparison"]["upside"] == pytest.approx(-46.44)


def test_approved_import_requires_an_existing_exact_batch_and_never_creates_one():
    with pytest.raises(ValueError, match="exact existing"):
        replay("approved-import", CLOCK)


@pytest.mark.parametrize("edits", [{"public_redistribution_allowed": True}, {"data_origin": "actual_ibkr"},
    {"identity": {"ticker": "AAPL", "cik": "0000320193"}}, {"currency": "EUR"}, {"price_timestamp": None}])
def test_unknown_incompatible_or_unauthorized_private_observations_fail(edits):
    observation = {"provider": "ibkr", "permitted_use": "personal_local_only", "public_redistribution_allowed": False,
        "data_origin": "simulated_ibkr", "price": 100.0, "currency": "USD", "price_timestamp": CLOCK,
        "identity": {"ticker": "MSFT", "cik": "0000789019"}, **edits}
    with pytest.raises(ValueError):
        _private_ibkr(observation)


def simulated_native_export():
    """Synthetic native-CLI shape; no broker or subscription is exercised."""
    identity = {"ticker": "MSFT", "cik": "0000789019", "issuer_id": "synthetic-issuer", "instrument_id": "synthetic-instrument", "listing_id": "synthetic-listing"}
    quote = {"provider": "ibkr", "permitted_use": "personal_local_only", "public_redistribution_allowed": False,
        "data_origin": "actual_ibkr", "identity": identity, "price": 100.0, "currency": "USD", "price_timestamp": CLOCK,
        "retrieved_at": CLOCK, "market_data_type": "live", "source_security": {"con_id": 123, "symbol": "MSFT", "local_symbol": "MSFT",
        "security_type": "STK", "primary_exchange": "NASDAQ", "currency": "USD", "trading_class": "MSFT"}}
    quote["observation_sha256"] = hashlib.sha256(json.dumps(quote, sort_keys=True).encode()).hexdigest()
    return {"schema_version": "fairworth-private-ibkr-1", "provider": "ibkr", "permitted_use": "personal_local_only",
        "public_redistribution_allowed": False, "data_origin": "actual_ibkr", "source_retention": True,
        "scope": deepcopy(identity), "quote": quote, "plan": {"ignored_test_field": "not_exported"}, "history": []}


def test_native_cli_export_replays_original_quote_without_losing_hash_or_private_scope():
    envelope = simulated_native_export()
    original = deepcopy(envelope)
    selected = _private_ibkr(envelope, "offline-test-receipt", envelope["scope"])
    assert selected["price"] == envelope["quote"]["price"]
    assert selected["identity"] == envelope["scope"]
    assert selected["permitted_use"] == "personal_local_only"
    assert "plan" not in selected and "history" not in selected
    assert envelope == original


@pytest.mark.parametrize("edit", ["version", "scope", "permission", "retention", "hash", "receipt"])
def test_invalid_native_export_cannot_bypass_original_quote_validation(edit):
    envelope = simulated_native_export()
    receipt = "offline-test-receipt"
    if edit == "version": envelope["schema_version"] = "unknown"
    elif edit == "scope": envelope["scope"]["listing_id"] = "wrong-listing"
    elif edit == "permission": envelope["public_redistribution_allowed"] = True
    elif edit == "retention": envelope["source_retention"] = False
    elif edit == "hash": envelope["quote"]["price"] = 101.0
    else: receipt = None
    with pytest.raises(ValueError):
        _private_ibkr(envelope, receipt)
