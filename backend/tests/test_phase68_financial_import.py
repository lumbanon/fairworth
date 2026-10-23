"""Guarded SEC import contracts use small synthetic facts and local databases."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.models import CacheEntry, Company, FinancialFact, FinancialImportBatch, FinancialSnapshot
from app.registry.repository import SecurityRegistryRepository
from app.repositories.financial_repository import FinancialRepository, content_hash
from app.services.financial_import_service import apply_preview, build_preview
from app.services.normalization import extract_observations, normalize_company_facts
from phase66_coverage_helpers import import_captured_listings


CLOCK = "2026-10-22T06:51:30Z"


def retained_source(tmp_path, raw, ticker="AAPL"):
    path = tmp_path / f"{ticker}.json"
    manifest = tmp_path / f"{ticker}-manifest.json"
    data = json.dumps(raw).encode()
    path.write_bytes(data)
    cik = str(raw["cik"]).zfill(10)
    row = {"file": path.name, "status": "received", "http_status": 200,
           "cik": cik, "url": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
           "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "retrieved_at": "2026-10-20T12:00:00Z"}
    manifest.write_text(json.dumps({"attempts": [row]}))
    return {"source": str(path), "manifest": str(manifest), "ticker": ticker}


@pytest.fixture
def import_case(session_factory, tmp_path, raw_facts):
    import_captured_listings(session_factory)
    raw = deepcopy(raw_facts)
    raw["cik"] = 320193
    return raw, retained_source(tmp_path, raw)


def preview(engine, spec):
    return build_preview(engine, [spec], as_of=CLOCK, sec_cache_ttl_seconds=21600)


def confirm(plan):
    return f"APPLY {plan['preview_digest']}"


def counts(factory):
    with factory() as session:
        return {model.__tablename__: session.scalar(select(func.count()).select_from(model))
                for model in (Company, FinancialFact, FinancialSnapshot, CacheEntry, FinancialImportBatch)}


def test_exact_preview_apply_and_repeat_are_idempotent(engine, session_factory, import_case):
    raw, spec = import_case
    before = counts(session_factory)
    plan = preview(engine, spec)
    assert counts(session_factory) == before
    assert plan["totals"]["company_inserts"] == plan["totals"]["snapshot_inserts"] == 1
    assert plan["totals"]["new_observations"] == 24
    result = apply_preview(engine, plan, confirmation=confirm(plan))
    assert result["row_changes"] == {"companies": 1, "financial_facts": 24, "financial_snapshots": 1}
    after = counts(session_factory)
    assert apply_preview(engine, plan, confirmation=confirm(plan))["already_applied"] is True
    assert counts(session_factory) == after
    next_plan = preview(engine, spec)
    assert next_plan["totals"]["new_observations"] == next_plan["totals"]["snapshot_inserts"] == 0
    second = apply_preview(engine, next_plan, confirmation=confirm(next_plan))
    assert second["row_changes"] == {"companies": 0, "financial_facts": 0, "financial_snapshots": 0}
    with session_factory() as session:
        fact = session.scalar(select(FinancialFact))
        assert fact.retrieved_at.isoformat().startswith("2026-10-20T12:00:00")
        assert fact.original_source["accn"] == raw["facts"]["us-gaap"][fact.concept]["units"][fact.unit][0]["accn"]
        cached = session.get(CacheEntry, result["imported"][0]["source_cache_key"])
        assert cached.expires_at.isoformat().startswith("2026-10-20T18:00:00")
        assert cached.payload == raw


@pytest.mark.parametrize("confirmation", ["", "yes", "APPLY other"])
def test_unauthorized_apply_rejected(engine, session_factory, import_case, confirmation):
    _, spec = import_case
    plan = preview(engine, spec)
    before = counts(session_factory)
    with pytest.raises(ValueError, match="explicit operator confirmation"):
        apply_preview(engine, plan, confirmation=confirmation)
    assert counts(session_factory) == before


def test_tampered_preview_or_source_rejected(engine, session_factory, import_case):
    _, spec = import_case
    plan = preview(engine, spec)
    altered = deepcopy(plan)
    altered["totals"]["new_observations"] += 1
    with pytest.raises(ValueError, match="intact preview"):
        apply_preview(engine, altered, confirmation=confirm(plan))
    with open(spec["source"], "ab") as stream:
        stream.write(b" ")
    with pytest.raises(ValueError, match="Source bytes"):
        apply_preview(engine, plan, confirmation=confirm(plan))
    assert counts(session_factory)["financial_facts"] == 0


def test_missing_original_hash_rejected(engine, import_case):
    _, spec = import_case
    manifest = json.loads(open(spec["manifest"]).read())
    del manifest["attempts"][0]["sha256"]
    with open(spec["manifest"], "w") as stream:
        json.dump(manifest, stream)
    with pytest.raises(ValueError, match="Source bytes"):
        preview(engine, spec)


def test_wrong_cik_and_ambiguous_owner_rejected(engine, session_factory, import_case):
    raw, spec = import_case
    raw["cik"] = 789019
    wrong = retained_source(Path(spec["source"]).parent, raw)
    with pytest.raises(ValueError, match="selected registered issuer"):
        preview(engine, wrong)
    raw["cik"] = 320193
    spec = retained_source(Path(spec["source"]).parent, raw)
    identity = SecurityRegistryRepository(session_factory).resolve("AAPL")
    with session_factory.begin() as session:
        session.add_all([Company(ticker=ticker, issuer_id=identity["issuer_id"], cik=identity["cik"], name="Synthetic")
                         for ticker in ("AAPL", "AAPL.OLD")])
    with pytest.raises(ValueError, match="ownership conflicts"):
        preview(engine, spec)


def test_same_filing_conflict_blocks_without_overwriting(engine, session_factory, import_case):
    raw, spec = import_case
    identity = SecurityRegistryRepository(session_factory).resolve("AAPL")
    repo = FinancialRepository(session_factory)
    company_id = repo.save_company(identity)
    repo.save_financials(company_id, extract_observations(raw), normalize_company_facts(raw, cik=identity["cik"]))
    changed = deepcopy(raw)
    changed["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"][-1]["val"] += 5
    spec = retained_source(Path(spec["source"]).parent, changed)
    plan = preview(engine, spec)
    assert plan["apply_blocked"] is True
    assert plan["totals"]["same_filing_conflicts"] == 1
    with pytest.raises(ValueError, match="Conflicting source facts"):
        apply_preview(engine, plan, confirmation=confirm(plan))
    assert counts(session_factory)["financial_facts"] == 24


def test_new_filing_preserves_competing_observations_and_history(engine, session_factory, import_case):
    raw, spec = import_case
    original = preview(engine, spec)
    apply_preview(engine, original, confirmation=confirm(original))
    with session_factory() as session:
        old = {row.id: content_hash(row.original_source) for row in session.scalars(select(FinancialFact))}
    amended = deepcopy(raw)
    item = deepcopy(amended["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"][-1])
    item.update(val=item["val"] + 5, accn="0000320193-25-000002", filed="2025-03-01", form="10-K/A")
    amended["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"].append(item)
    spec = retained_source(Path(spec["source"]).parent, amended)
    plan = preview(engine, spec)
    assert plan["totals"]["restatement_review_candidates"] == 1
    apply_preview(engine, plan, confirmation=confirm(plan))
    with session_factory() as session:
        assert all(content_hash(session.get(FinancialFact, key).original_source) == value for key, value in old.items())
        assert session.scalar(select(func.count()).select_from(FinancialFact)) == 25
        assert session.scalar(select(func.count()).select_from(FinancialSnapshot)) == 2


def test_failure_rolls_back_whole_import_including_cache_and_batch(engine, session_factory, import_case):
    _, spec = import_case
    plan = preview(engine, spec)
    before = counts(session_factory)
    def fail(_session, _report):
        raise RuntimeError("Injected transaction failure")
    with pytest.raises(RuntimeError, match="Injected"):
        apply_preview(engine, plan, confirmation=confirm(plan), fault_hook=fail)
    assert counts(session_factory) == before
    assert apply_preview(engine, plan, confirmation=confirm(plan))["row_changes"]["financial_facts"] == 24


def test_database_drift_requires_new_preview(engine, session_factory, import_case):
    _, spec = import_case
    plan = preview(engine, spec)
    identity = SecurityRegistryRepository(session_factory).resolve("MSFT")
    FinancialRepository(session_factory).save_company(identity)
    with pytest.raises(ValueError, match="Database changed"):
        apply_preview(engine, plan, confirmation=confirm(plan))
    assert counts(session_factory)["financial_facts"] == 0


def test_one_alphabet_owner_is_shared_and_duplicate_issuer_sources_rejected(engine, session_factory, tmp_path, raw_facts):
    import_captured_listings(session_factory)
    raw = deepcopy(raw_facts)
    raw["cik"] = 1652044
    spec = retained_source(tmp_path, raw, ticker="GOOGL")
    plan = preview(engine, spec)
    apply_preview(engine, plan, confirmation=confirm(plan))
    spec["ticker"] = "GOOG"
    next_plan = preview(engine, spec)
    assert next_plan["totals"]["company_inserts"] == next_plan["totals"]["new_observations"] == 0
    apply_preview(engine, next_plan, confirmation=confirm(next_plan))
    assert counts(session_factory)["companies"] == 1
    with pytest.raises(ValueError, match="multiple securities"):
        build_preview(engine, [spec, {**spec, "ticker": "GOOGL"}], as_of=CLOCK, sec_cache_ttl_seconds=21600)


def test_existing_ticker_from_other_issuer_is_never_reassigned(engine, session_factory, import_case):
    _, spec = import_case
    other = SecurityRegistryRepository(session_factory).resolve("MSFT")
    old_id = FinancialRepository(session_factory).save_company({**other, "ticker": "AAPL"})
    plan = preview(engine, spec)
    apply_preview(engine, plan, confirmation=confirm(plan))
    with session_factory() as session:
        assert session.get(Company, old_id).issuer_id == other["issuer_id"]
        assert counts(session_factory)["companies"] == 2


def test_imported_issuer_snapshot_and_sources_load_without_http(engine, session_factory, import_case):
    import asyncio
    from app.services.cache_service import CacheService
    from app.services.financial_service import FinancialService
    _, spec = import_case
    plan = preview(engine, spec)
    applied = apply_preview(engine, plan, confirmation=confirm(plan))
    identity = SecurityRegistryRepository(session_factory).resolve("AAPL")
    class Companies:
        async def company_identity(self, _ticker, **_scope):
            return identity, SimpleNamespace(warnings=[], status="fresh")
    class NoNetwork:
        async def facts(self, *_args):
            pytest.fail("An explicitly imported snapshot must load without SEC HTTP.")
    service = FinancialService(Companies(), NoNetwork(), CacheService(session_factory),
        FinancialRepository(session_factory), SimpleNamespace(sec_cache_ttl_seconds=21600))
    response = asyncio.run(service.statements("AAPL", "annual", 10))
    assert len(response["periods"]) == 2
    assert response["financial_import"]["import_batch_id"] == applied["batch_id"]
    assert response["financial_import"]["source_sha256"] == plan["sources"][0]["source"]["sha256"]
    assert response["retrieved_at"].isoformat().startswith("2026-10-20T12:00:00")
    assert response["status"] == "stale"


def test_newer_cache_is_preserved_and_takes_precedence(engine, session_factory, import_case):
    raw, spec = import_case
    instant = datetime(2026, 10, 21, tzinfo=timezone.utc)
    with session_factory.begin() as session:
        session.add(CacheEntry(key="sec:facts:0000320193", payload={**raw, "newer": True},
            retrieved_at=instant, expires_at=datetime(2026, 10, 22, tzinfo=timezone.utc), provider="sec-edgar"))
    plan = preview(engine, spec)
    result = apply_preview(engine, plan, confirmation=confirm(plan))
    assert result["cache_writes"] == 1
    identity = SecurityRegistryRepository(session_factory).resolve("AAPL")
    assert FinancialRepository(session_factory).imported_dataset(identity["issuer_id"], identity["cik"]) is None
    with session_factory() as session:
        assert session.get(CacheEntry, "sec:facts:0000320193").payload["newer"] is True


def test_invariant_violation_rolls_back_unrelated_row_mutation(engine, session_factory, import_case):
    _, spec = import_case
    other = SecurityRegistryRepository(session_factory).resolve("MSFT")
    old_id = FinancialRepository(session_factory).save_company(other)
    plan = preview(engine, spec)
    def corrupt(session, _report):
        session.get(Company, old_id).name = "Changed unrelated company"
    with pytest.raises(ValueError, match="Existing financial rows changed"):
        apply_preview(engine, plan, confirmation=confirm(plan), fault_hook=corrupt)
    with session_factory() as session:
        assert session.get(Company, old_id).name == other["name"]
    assert counts(session_factory)["financial_facts"] == 0


def test_cli_cannot_overwrite_preview_or_sources(tmp_path, monkeypatch):
    import importlib.util
    import sys
    source = tmp_path / "source.json"
    manifest = tmp_path / "manifest.json"
    source.write_text("original")
    manifest.write_text("original")
    path = Path(__file__).resolve().parents[1] / "scripts" / "import_sec_financials.py"
    spec = importlib.util.spec_from_file_location("phase68_import_cli", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(sys, "argv", [str(path), "preview", "--manifest", str(manifest),
        "--source", f"AAPL={source}", "--as-of", CLOCK, "--output", str(source)])
    with pytest.raises(SystemExit) as error:
        module.main()
    assert error.value.code == 2
    assert source.read_text() == "original"


def test_repeat_batch_still_refuses_source_and_manifest_changed_together(engine, import_case):
    raw, spec = import_case
    plan = preview(engine, spec)
    apply_preview(engine, plan, confirmation=confirm(plan))
    changed = deepcopy(raw)
    changed["entityName"] = "Changed acquired source"
    retained_source(Path(spec["source"]).parent, changed)
    with pytest.raises(ValueError, match="exact reviewed preview"):
        apply_preview(engine, plan, confirmation=confirm(plan))


def test_same_accession_cannot_hide_conflict_by_relabeling_filed_or_form(engine, session_factory, import_case):
    raw, spec = import_case
    plan = preview(engine, spec)
    apply_preview(engine, plan, confirmation=confirm(plan))
    altered = deepcopy(raw)
    fact = altered["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"][-1]
    fact.update(val=fact["val"] + 5, filed="2025-03-01", form="10-K/A")
    spec = retained_source(Path(spec["source"]).parent, altered)
    next_plan = preview(engine, spec)
    assert next_plan["apply_blocked"]
    assert next_plan["totals"]["same_filing_conflicts"] == 1
    assert counts(session_factory)["financial_facts"] == 24


def test_old_raw_source_is_preserved_and_import_adds_separate_version(engine, session_factory, import_case):
    raw, spec = import_case
    old_clock = datetime(2026, 10, 19, tzinfo=timezone.utc)
    old_payload = {**raw, "old_source": True}
    with session_factory.begin() as session:
        session.add(CacheEntry(key="sec:facts:0000320193", payload=old_payload,
            retrieved_at=old_clock, expires_at=old_clock, provider="sec-edgar"))
    plan = preview(engine, spec)
    result = apply_preview(engine, plan, confirmation=confirm(plan))
    with session_factory() as session:
        original = session.get(CacheEntry, "sec:facts:0000320193")
        assert original.payload == old_payload
        assert original.retrieved_at.isoformat().startswith("2026-10-19T00:00:00")
        version = session.get(CacheEntry, result["imported"][0]["source_cache_key"])
        assert version.payload == raw
    identity = SecurityRegistryRepository(session_factory).resolve("AAPL")
    assert FinancialRepository(session_factory).imported_dataset(identity["issuer_id"], identity["cik"]) is not None


def test_source_and_manifest_changed_after_inventory_roll_back_atomically(engine, session_factory, import_case, monkeypatch):
    import app.services.financial_import_service as importer
    raw, spec = import_case
    plan = preview(engine, spec)
    before = counts(session_factory)
    original = importer._inventory
    def mutate_after_inventory(*args, **kwargs):
        reports = original(*args, **kwargs)
        changed = deepcopy(raw)
        changed["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"][-1]["val"] += 5
        retained_source(Path(spec["source"]).parent, changed)
        return reports
    monkeypatch.setattr(importer, "_inventory", mutate_after_inventory)
    with pytest.raises(ValueError, match="changed during apply"):
        apply_preview(engine, plan, confirmation=confirm(plan))
    assert counts(session_factory) == before


def test_normalization_change_after_inventory_rolls_back_inserted_facts(engine, session_factory, import_case, monkeypatch):
    import app.services.financial_import_service as importer
    _, spec = import_case
    plan = preview(engine, spec)
    before = counts(session_factory)
    original_inventory = importer._inventory
    original_normalize = importer.normalize_company_facts
    def switch_after_inventory(*args, **kwargs):
        reports = original_inventory(*args, **kwargs)
        def changed(*normalize_args, **normalize_kwargs):
            result = original_normalize(*normalize_args, **normalize_kwargs)
            result["unreviewed_interpretation"] = True
            return result
        monkeypatch.setattr(importer, "normalize_company_facts", changed)
        return reports
    monkeypatch.setattr(importer, "_inventory", switch_after_inventory)
    with pytest.raises(ValueError, match="reviewed snapshot"):
        apply_preview(engine, plan, confirmation=confirm(plan))
    assert counts(session_factory) == before


def test_valid_same_issuer_older_snapshot_cannot_inherit_new_source_provenance(engine, session_factory, import_case):
    from app.core.exceptions import ApiError
    raw, spec = import_case
    plan = preview(engine, spec)
    result = apply_preview(engine, plan, confirmation=confirm(plan))
    company_id = result["imported"][0]["company_id"]
    older = deepcopy(raw)
    for definition in older["facts"]["us-gaap"].values():
        for unit, values in definition["units"].items():
            definition["units"][unit] = values[:1]
    normalized = normalize_company_facts(older, cik="0000320193")
    FinancialRepository(session_factory).save_financials(company_id, extract_observations(older), normalized)
    with session_factory.begin() as session:
        old_snapshot = session.scalar(select(FinancialSnapshot).where(FinancialSnapshot.content_hash == content_hash(normalized)))
        batch = session.get(FinancialImportBatch, result["batch_id"])
        summary = deepcopy(batch.summary)
        summary["imported"][0].update(snapshot_id=old_snapshot.id, snapshot_hash=old_snapshot.content_hash)
        batch.summary = summary
    identity = SecurityRegistryRepository(session_factory).resolve("AAPL")
    with pytest.raises(ApiError, match="snapshot failed"):
        FinancialRepository(session_factory).imported_dataset(identity["issuer_id"], identity["cik"])


def test_import_summary_cannot_claim_different_source_hash_from_inventory(engine, session_factory, import_case):
    from app.core.exceptions import ApiError
    _, spec = import_case
    plan = preview(engine, spec)
    result = apply_preview(engine, plan, confirmation=confirm(plan))
    with session_factory.begin() as session:
        batch = session.get(FinancialImportBatch, result["batch_id"])
        summary = deepcopy(batch.summary)
        summary["imported"][0]["source_sha256"] = "0" * 64
        batch.summary = summary
    identity = SecurityRegistryRepository(session_factory).resolve("AAPL")
    with pytest.raises(ApiError, match="SEC source failed"):
        FinancialRepository(session_factory).imported_dataset(identity["issuer_id"], identity["cik"])
