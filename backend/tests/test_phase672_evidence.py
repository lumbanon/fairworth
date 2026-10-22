"""Synthetic offline controls for the separately authorized AAPL source receipt."""
from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json

import pytest

from scripts.phase672_evidence import load_aapl_manifest

CLOCK = "2026-10-21T16:00:00+00:00"
RECEIPT = "call_synthetic_phase672_consent"
ANNUAL = {"accessionNumber": "0000320193-25-000079", "filingDate": "2025-10-31",
          "reportDate": "2025-09-27", "primaryDocument": "aapl-20250927.htm"}


def save(tmp_path, manifest):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def record(tmp_path, endpoint, payload, offset):
    content = payload.encode() if isinstance(payload, str) else json.dumps(payload).encode()
    filename = endpoint + ".raw"
    (tmp_path / filename).write_bytes(content)
    urls = {"submissions": "https://data.sec.gov/submissions/CIK0000320193.json",
            "companyfacts": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
            "annual-primary": "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm"}
    return {"provider": "sec", "endpoint": endpoint, "url": urls[endpoint], "parameters": {}, "symbol": "AAPL", "cik": "0000320193",
            "byte_limit": {"submissions": 2_000_000, "companyfacts": 12_000_000, "annual-primary": 8_000_000}[endpoint],
            "started_at": f"2026-10-21T15:00:{offset:02}+00:00", "retrieved_at": f"2026-10-21T15:00:{offset+1:02}+00:00",
            "status": "received", "http_status": 200, "file": filename, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}


def fixture(tmp_path):
    submissions = {"cik": "0000320193", "filings": {"recent": {"form": ["10-K"], **{key: [value] for key, value in ANNUAL.items()}}}}
    annual = '<html><ix:nonNumeric name="dei:EntityCentralIndexKey">0000320193</ix:nonNumeric><ix:nonNumeric name="dei:DocumentPeriodEndDate"><ix:nonNumeric name="dei:CurrentFiscalYearEndDate">September&#160;27</ix:nonNumeric>, 2025</ix:nonNumeric></html>'
    records = [record(tmp_path, "submissions", submissions, 1), record(tmp_path, "companyfacts", {"cik": 320193, "facts": {}}, 3), record(tmp_path, "annual-primary", annual, 5)]
    manifest = {"schema_version": "phase672-aapl-acquisition-1", "authorization_question_id": RECEIPT, "authorization": "Synthetic receipt; independent consent must be verified by caller.",
        "maximum_requests": 7, "maximum_bytes": 30_000_000, "timeout_seconds": 30, "retries": 0, "redirects": False, "concurrency": 1,
        "started_at": "2026-10-21T15:00:00+00:00", "requests": records, "complete": True, "selected_annual_filing": deepcopy(ANNUAL),
        "finished_at": "2026-10-21T15:00:07+00:00", "actual_requests": len(records), "actual_bytes": sum(row["bytes"] for row in records), "stopped_providers": []}
    return save(tmp_path, manifest), manifest


def load(path, receipt=RECEIPT):
    return load_aapl_manifest(path, audit_clock=CLOCK, authorization_receipt=receipt)


def test_original_submissions_and_nested_inline_annual_identity_are_independently_verified(tmp_path):
    path, manifest = fixture(tmp_path)
    before = deepcopy(manifest)
    result = load(path)
    assert manifest == before
    assert result["actual_requests"] == 3 and result["actual_bytes"] == manifest["actual_bytes"]
    assert result["inventory"][-1]["source_summary"]["status"] == "validated_original_annual_identity"
    assert result["authorization_verification"] == "caller_supplied_receipt_not_independent_consent"
    assert all("payload" not in row for row in result["safe_metadata"]["requests"])


@pytest.mark.parametrize("change", [
    {"cik": "0000789019"}, {"symbol": "MSFT"}, {"url": "https://evil.invalid/filing"},
    {"parameters": {"apikey": "private_control"}}, {"byte_limit": 20_000_000}, {"bytes": 12_000_001},
    {"file": "../.env"}, {"sha256": "0"*64}, {"retrieved_at": "2027-01-01T00:00:00+00:00"},
    {"started_at": "2026-10-21T15:00:00"}, {"http_status": True},
])
def test_invalid_scope_hash_size_path_metadata_and_clocks_fail_without_private_output(tmp_path, change):
    path, manifest = fixture(tmp_path)
    manifest["requests"][1].update(change)
    save(tmp_path, manifest)
    with pytest.raises(ValueError) as error:
        load(path)
    assert "private_control" not in str(error.value)


@pytest.mark.parametrize("change", [{"maximum_requests": 8}, {"maximum_bytes": 40_000_000}, {"retries": 1},
    {"redirects": True}, {"concurrency": 2}, {"complete": False}, {"actual_bytes": 1}, {"actual_requests": 4}])
def test_approval_limits_and_completion_totals_cannot_be_extended(tmp_path, change):
    path, manifest = fixture(tmp_path)
    manifest.update(change)
    save(tmp_path, manifest)
    with pytest.raises(ValueError):
        load(path)


def test_receipt_is_required_and_does_not_establish_user_consent_by_itself(tmp_path):
    path, _ = fixture(tmp_path)
    with pytest.raises(ValueError, match="authorization mismatch"):
        load(path, "call_different_receipt_control")


def test_annual_cannot_point_to_another_filing_or_follow_forged_selected_metadata(tmp_path):
    path, manifest = fixture(tmp_path)
    manifest["selected_annual_filing"]["primaryDocument"] = "other.htm"
    save(tmp_path, manifest)
    with pytest.raises(ValueError, match="submissions proof"):
        load(path)


def test_wrong_annual_html_issuer_is_rejected_even_with_a_new_matching_local_hash(tmp_path):
    path, manifest = fixture(tmp_path)
    raw = (tmp_path / "annual-primary.raw").read_bytes().replace(b"0000320193", b"0000789019")
    (tmp_path / "annual-primary.raw").write_bytes(raw)
    manifest["requests"][-1].update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    save(tmp_path, manifest)
    with pytest.raises(ValueError, match="issuer or reporting period"):
        load(path)


def test_market_quote_future_clock_is_rejected_and_denial_prevents_further_fmp_calls(tmp_path):
    path, manifest = fixture(tmp_path)
    payload = [{"symbol": "AAPL", "price": 100, "timestamp": int(datetime(2027, 1, 1, tzinfo=UTC).timestamp())}]
    content = json.dumps(payload).encode(); (tmp_path / "quote.raw").write_bytes(content)
    quote = {"provider": "fmp", "endpoint": "quote", "url": "https://financialmodelingprep.com/stable/quote", "parameters": {"symbol": "AAPL"}, "symbol": "AAPL", "cik": "0000320193", "byte_limit": 1_000_000,
        "started_at": "2026-10-21T15:00:00+00:00", "retrieved_at": "2026-10-21T15:00:00.5+00:00", "status": "received", "http_status": 200,
        "file": "quote.raw", "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
    manifest["requests"] = [quote]
    manifest.update(actual_requests=1, actual_bytes=len(content))
    save(tmp_path, manifest)
    with pytest.raises(ValueError, match="future quote"):
        load(path)
    quote.update(status="http_error", http_status=402)
    duplicate = deepcopy(quote)
    duplicate.update(endpoint="splits", url="https://financialmodelingprep.com/stable/splits", parameters={"symbol": "AAPL", "limit": 1000},
        started_at="2026-10-21T15:00:02+00:00", retrieved_at="2026-10-21T15:00:03+00:00")
    manifest["requests"].append(duplicate)
    manifest.update(actual_requests=2, actual_bytes=2*len(content), stopped_providers=["fmp"])
    save(tmp_path, manifest)
    with pytest.raises(ValueError, match="provider denial"):
        load(path)
