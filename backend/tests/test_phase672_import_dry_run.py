"""Original-source comparisons preserve populated data and cannot apply writes."""
from copy import deepcopy
import hashlib
import json
import importlib.util
from pathlib import Path
import sys

import pytest
from sqlalchemy import select, func, text
from sqlalchemy.exc import DBAPIError

from app.models import FinancialFact
from app.registry.repository import SecurityRegistryRepository
from app.repositories.financial_repository import FinancialRepository, content_hash
from app.services.financial_import_audit import audit_financial_import, read_only_connection, load_approved_sec_source
from app.services.normalization import normalize_company_facts, extract_observations
from phase66_coverage_helpers import import_captured_listings


def source(raw):
    return {"mode": "synthetic_test", "cik": "0000320193", "canonical_payload_sha256": content_hash(raw),
            "sha256": "0" * 64, "retrieved_at": "2026-10-20T00:00:00Z"}


@pytest.fixture
def populated(session_factory, raw_facts):
    import_captured_listings(session_factory)
    company = SecurityRegistryRepository(session_factory).resolve("AAPL")
    raw = deepcopy(raw_facts)
    raw["cik"] = 320193
    repository = FinancialRepository(session_factory)
    company_id = repository.save_company(company)
    repository.save_financials(company_id, extract_observations(raw), normalize_company_facts(raw, cik="0000320193"))
    return raw


def audit(engine, raw):
    with read_only_connection(engine) as connection:
        return audit_financial_import(connection, raw, source(raw), ticker="AAPL", as_of="2026-10-21T00:00:00Z", sec_cache_ttl_seconds=21600)


def test_all_existing_observations_are_duplicates_and_no_write_path_exists(engine, populated):
    report = audit(engine, populated)
    assert report["facts"]["already_persisted"] == report["facts"]["incoming_unique"]
    assert report["facts"]["new_observations"] == report["facts"]["same_filing_conflicts"] == 0
    assert report["write_plan"]["apply_supported"] is False
    assert report["write_plan"]["executed_writes"] == 0
    assert report["cache_consequences"]["source_within_configured_cache_policy"] is False
    assert report["write_plan"]["potential_company_metadata_updates"] == 1
    assert "not an asserted provider expiry" in report["cache_consequences"]["cache_expiry_basis"]


def test_changed_original_value_in_same_filing_is_quarantined_not_overwritten(engine, populated):
    raw = deepcopy(populated)
    raw["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"][-1]["val"] += 1
    with engine.connect() as connection:
        before = connection.scalar(select(func.count()).select_from(FinancialFact))
    report = audit(engine, raw)
    assert report["facts"]["same_filing_conflicts"] == 1
    assert report["write_plan"]["scope_conflicts_require_review"] is True
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(FinancialFact)) == before


def test_filing_frame_relabeling_cannot_hide_conflicting_source_value(engine, populated):
    raw = deepcopy(populated)
    changed = raw["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"][-1]
    changed["val"] += 1
    changed["frame"] = "another-calendar-label"
    changed["fy"] = 1999
    changed["fp"] = "Q4"
    report = audit(engine, raw)
    assert report["facts"]["same_filing_conflicts"] == 1
    assert report["facts"]["new_observations"] == 1
    assert report["write_plan"]["scope_conflicts_require_review"] is True
    assert report["write_plan"]["executed_writes"] == 0


@pytest.mark.parametrize("destination", ["source", "manifest"])
def test_cli_cannot_overwrite_original_source_or_manifest(tmp_path, monkeypatch, destination):
    source_path, manifest_path = tmp_path / "source.json", tmp_path / "manifest.json"
    source_path.write_text("original financial evidence", encoding="utf-8")
    manifest_path.write_text("original acquisition manifest", encoding="utf-8")
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "audit_financial_import.py"
    spec = importlib.util.spec_from_file_location("phase672_dryrun_cli", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(sys, "argv", [str(script_path), "--source", str(source_path), "--manifest", str(manifest_path),
        "--ticker", "AAPL", "--as-of", "2026-10-21T00:00:00Z", "--output", str(source_path if destination == "source" else manifest_path)])
    with pytest.raises(SystemExit) as error:
        module.main()
    assert error.value.code == 2
    assert source_path.read_text(encoding="utf-8") == "original financial evidence"
    assert manifest_path.read_text(encoding="utf-8") == "original acquisition manifest"


def test_read_only_transaction_rejects_mutation(engine, populated):
    with pytest.raises(DBAPIError):
        with read_only_connection(engine) as connection:
            connection.execute(text("DELETE FROM financial_facts"))
    assert audit(engine, populated)["facts"]["new_observations"] == 0


def test_wrong_reporting_issuer_cannot_be_import_target(engine, populated):
    raw = deepcopy(populated)
    raw["cik"] = 789019
    wrong = {**source(raw), "cik": "0000789019"}
    with pytest.raises(ValueError, match="selected registered issuer"):
        with read_only_connection(engine) as connection:
            audit_financial_import(connection, raw, wrong, ticker="AAPL", as_of="2026-10-21T00:00:00Z", sec_cache_ttl_seconds=21600)


def test_source_loader_requires_exact_original_bytes_and_cik(tmp_path, raw_facts):
    path, manifest = tmp_path / "source.json", tmp_path / "manifest.json"
    raw = deepcopy(raw_facts); raw["cik"] = 320193
    content = json.dumps(raw).encode(); path.write_bytes(content)
    row = {"file": path.name, "status": "received", "http_status": 200, "cik": "0000320193",
           "url": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json", "bytes": len(content),
           "sha256": hashlib.sha256(content).hexdigest(), "retrieved_at": "2026-10-20T00:00:00Z"}
    manifest.write_text(json.dumps({"attempts": [row]}))
    assert load_approved_sec_source(path, manifest)[0]["cik"] == 320193
    path.write_bytes(content + b" ")
    with pytest.raises(ValueError, match="Source bytes"):
        load_approved_sec_source(path, manifest)
