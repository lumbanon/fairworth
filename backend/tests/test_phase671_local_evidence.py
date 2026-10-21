"""Offline source-receipt validation; all payloads below are synthetic controls."""
from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json

import pytest

from scripts.phase671_evidence import load_local_evidence_manifest


AUDIT = "2026-10-21T00:10:00+00:00"
RECEIPT = "call_synthetic_approval_control"


def write_receipt(tmp_path, *, payload=None, provider="fmp", endpoint="quote", status="received", code=200):
    if payload is None:
        payload = [{"symbol": "MSFT", "price": 100, "timestamp": int(datetime(2026, 10, 20, 20, tzinfo=UTC).timestamp())}]
    content = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    (tmp_path / "one.raw").write_bytes(content)
    record = {"provider": provider, "endpoint": endpoint,
        "url": "https://financialmodelingprep.com/stable/" + endpoint,
        "symbol": "MSFT", "cik": "0000789019", "byte_limit": 1_000_000,
        "started_at": "2026-10-21T00:00:01+00:00", "retrieved_at": "2026-10-21T00:00:02+00:00",
        "status": status, "http_status": code, "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(), "file": "one.raw"}
    receipt = {"schema_version": "phase671-acquisition-1", "authorization": "Synthetic test receipt; does not prove real consent.",
        "authorization_question_id": RECEIPT, "started_at": "2026-10-21T00:00:00+00:00",
        "finished_at": "2026-10-21T00:00:03+00:00", "complete": True,
        "limits": {"requests": 20, "bytes": 40_000_000, "timeout_seconds": 30, "retries": 0, "redirects": False, "concurrency": 1},
        "requests": [record], "actual_requests": 1, "actual_bytes": len(content),
        "stopped_providers": [provider] if code in {401, 402, 403, 429} or status in {"provider_error", "invalid_json", "transport_error", "size_limit_exceeded"} else []}
    return save(tmp_path, receipt), receipt


def save(tmp_path, receipt):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    return path


def load(path, **kwargs):
    return load_local_evidence_manifest(path, audit_clock=AUDIT, expected_authorization_question_id=RECEIPT, **kwargs)


def test_valid_inventory_is_explicitly_not_an_independent_consent_or_eligibility_claim(tmp_path):
    path, receipt = write_receipt(tmp_path)
    original = deepcopy(receipt)
    result = load(path)
    assert receipt == original
    assert result["actual_requests"] == 1 and result["actual_bytes"] == receipt["actual_bytes"]
    assert result["authorization"]["verification"] == "caller_supplied_receipt_not_independent_consent"
    assert result["inventory"][0]["payload"][0]["price"] == 100
    assert result["inventory"][0]["source_summary"]["status"] == "validated_raw_market_inventory"
    assert any("eligibility" in message for message in result["limitations"])


@pytest.mark.parametrize("change", [
    {"symbol": "GOOG"}, {"cik": "0000320193"}, {"url": "https://evil.example/quote"},
    {"url": "https://financialmodelingprep.com/stable/quote?apikey=private_control"},
    {"endpoint": "balance-sheet-statement"}, {"byte_limit": 2_000_000}, {"bytes": 1_000_001},
    {"sha256": "0" * 64}, {"file": "../backend/.env"}, {"started_at": "2026-10-21T00:00:01"},
    {"retrieved_at": "2026-10-22T00:00:00+00:00"}, {"status": "reserved"},
    {"http_status": 302}, {"api_key": "private_control"},
])
def test_invalid_request_receipts_are_rejected_without_exposing_private_fields(tmp_path, change):
    path, receipt = write_receipt(tmp_path)
    receipt["requests"][0].update(change)
    save(tmp_path, receipt)
    with pytest.raises(ValueError) as error:
        load(path)
    assert "private_control" not in str(error.value)


@pytest.mark.parametrize("change", [
    {"complete": False}, {"actual_requests": 2}, {"actual_bytes": 5},
    {"authorization_question_id": "call_wrong_receipt_control"},
    {"finished_at": "2026-10-22T00:00:00+00:00"},
    {"authorization": "contact control@example.test"},
])
def test_invalid_top_level_receipts_are_rejected(tmp_path, change):
    path, receipt = write_receipt(tmp_path)
    receipt.update(change)
    save(tmp_path, receipt)
    with pytest.raises(ValueError):
        load(path)


@pytest.mark.parametrize("payload", [
    [{"symbol": "AAPL", "price": 100, "timestamp": 1}],
    [{"symbol": "MSFT", "cik": "0000320193", "price": 100, "timestamp": 1}],
    [{"symbol": "MSFT", "price": 100, "timestamp": 1e30}],
    [{"symbol": "MSFT", "price": 100, "timestamp": 1_900_000_000}],
    [{"symbol": "MSFT", "inputs": {"fair_value": 100}}],
    {"inputs": {"fair_value": 100}},
    b'[{"symbol":"MSFT","symbol":"AAPL","price":100,"timestamp":1}]',
    b'[{"symbol":"MSFT","price":NaN,"timestamp":1}]',
])
def test_cross_security_nonfinite_future_or_serialized_model_inputs_are_not_source_evidence(tmp_path, payload):
    path, _ = write_receipt(tmp_path, payload=payload)
    with pytest.raises(ValueError):
        load(path)


def test_auth_denial_stays_unavailable_and_may_not_be_followed_by_another_provider_call(tmp_path):
    path, receipt = write_receipt(tmp_path, payload=b"Denied", status="http_error", code=402)
    result = load(path)
    assert result["inventory"][0]["payload"] is None
    assert result["inventory"][0]["source_summary"]["status"] == "unavailable_provider_response"
    second = deepcopy(receipt["requests"][0])
    second.update(endpoint="profile", url="https://financialmodelingprep.com/stable/profile",
                  started_at="2026-10-21T00:00:03+00:00", retrieved_at="2026-10-21T00:00:04+00:00")
    receipt["requests"].append(second)
    receipt.update(actual_requests=2, actual_bytes=2 * receipt["actual_bytes"], finished_at="2026-10-21T00:00:05+00:00")
    save(tmp_path, receipt)
    with pytest.raises(ValueError, match="after provider denial"):
        load(path)


def test_duplicate_request_and_under_one_second_spacing_are_rejected(tmp_path):
    path, receipt = write_receipt(tmp_path)
    second = deepcopy(receipt["requests"][0])
    receipt["requests"].append(second)
    save(tmp_path, receipt)
    with pytest.raises(ValueError, match="duplicate request"):
        load(path)
    second.update(endpoint="profile", url="https://financialmodelingprep.com/stable/profile",
                  started_at="2026-10-21T00:00:02.5+00:00", retrieved_at="2026-10-21T00:00:02.7+00:00")
    save(tmp_path, receipt)
    with pytest.raises(ValueError, match="minimum interval"):
        load(path)


def test_mutated_source_and_manifest_outside_allowed_directory_are_rejected(tmp_path):
    path, _ = write_receipt(tmp_path)
    (tmp_path / "one.raw").write_bytes(b"changed")
    with pytest.raises(ValueError, match="source size"):
        load(path)
    directory = tmp_path / "restricted"
    directory.mkdir()
    with pytest.raises(ValueError, match="outside the allowed"):
        load(path, allowed_root=directory)


def test_sec_directory_remains_reference_only_and_requires_exact_columns(tmp_path):
    payload = {"fields": ["cik", "name", "ticker", "exchange"], "data": [[789019, "Synthetic MSFT reference", "MSFT", "Nasdaq"]]}
    path, receipt = write_receipt(tmp_path, payload=payload)
    record = receipt["requests"][0]
    record.update(provider="sec", endpoint="company_tickers_exchange", symbol=None, cik=None,
                  url="https://www.sec.gov/files/company_tickers_exchange.json", byte_limit=5_000_000)
    save(tmp_path, receipt)
    result = load(path)
    assert result["inventory"][0]["source_summary"]["status"] == "parsed_issuer_reference_only"
    assert result["inventory"][0]["payload"] == payload


def test_split_dates_are_not_assumed_to_verify_completeness_or_current_share_class(tmp_path):
    payload = [{"date": "2024-06-10", "numerator": 10, "denominator": 1}]
    path, _ = write_receipt(tmp_path, endpoint="splits", payload=payload)
    result = load(path)
    assert result["inventory"][0]["source_summary"]["empty_response_is_not_verified_absence"]
    assert result["inventory"][0]["payload"] == payload
