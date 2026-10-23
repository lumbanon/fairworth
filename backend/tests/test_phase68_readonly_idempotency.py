"""Exact committed-import replay is independently verifiable without writes."""
from copy import deepcopy
from datetime import datetime, timezone
import os

import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from app.models import CacheEntry, Company, FinancialFact, FinancialImportBatch, FinancialSnapshot
from app.registry.repository import SecurityRegistryRepository
from app.repositories.financial_repository import FinancialRepository
from app.services.financial_import_service import apply_preview, verify_applied_preview
from app.services.financial_import_audit import read_only_connection
from app.services.normalization import extract_observations, normalize_company_facts
from test_phase68_financial_import import confirm, counts, import_case, preview  # noqa: F401


def applied(engine, import_case):
    _raw, spec = import_case
    plan = preview(engine, spec)
    result = apply_preview(engine, plan, confirmation=confirm(plan))
    return plan, result


def verify(engine, plan):
    return verify_applied_preview(engine, plan, confirmation=f"VERIFY {plan['preview_digest']}")


def test_readonly_replay_returns_exact_prior_receipt_without_lock_or_write(engine, session_factory, import_case):
    plan, result = applied(engine, import_case)
    before = counts(session_factory)
    statements = []
    def forbid_writes(_conn, _cursor, statement, _parameters, _context, _many):
        verb = statement.lstrip().split()[0].upper()
        assert verb in {"SELECT", "PRAGMA"}, statement
        statements.append(statement)
    event.listen(engine, "before_cursor_execute", forbid_writes)
    try:
        for _ in range(2):
            replay = verify(engine, plan)
            assert replay["receipt"] == {**result, "already_applied": True}
            assert replay["verification"] == {"mode": "read_only_applied_preview_verification",
                "executed_writes": 0, "verified_sources": 1, "verified_observations": 24,
                "preserved_original_facts": 0, "preserved_label_count": 0}
    finally:
        event.remove(engine, "before_cursor_execute", forbid_writes)
    assert any("PRAGMA query_only = ON" in statement for statement in statements)
    assert counts(session_factory) == before


def test_unapplied_preview_cannot_be_reported_as_idempotent(engine, import_case):
    _raw, spec = import_case
    plan = preview(engine, spec)
    with pytest.raises(ValueError, match="No exact committed import batch"):
        verify(engine, plan)


@pytest.mark.parametrize("confirmation", ["", "yes", "APPLY", "VERIFY other"])
def test_readonly_replay_requires_exact_confirmation(engine, import_case, confirmation):
    plan, _result = applied(engine, import_case)
    with pytest.raises(ValueError, match="explicit VERIFY confirmation"):
        verify_applied_preview(engine, plan, confirmation=confirmation)


def test_readonly_replay_rejects_tampered_reviewed_preview(engine, import_case):
    plan, _result = applied(engine, import_case)
    changed = deepcopy(plan)
    changed["totals"]["new_observations"] += 1
    with pytest.raises(ValueError, match="intact preview"):
        verify(engine, changed)


def test_readonly_replay_reopens_original_bytes(engine, import_case):
    plan, _result = applied(engine, import_case)
    with open(plan["sources"][0]["source_files"]["source"], "ab") as stream:
        stream.write(b" ")
    with pytest.raises(ValueError, match="Source bytes"):
        verify(engine, plan)


@pytest.mark.parametrize("mutation,error", [
    ("inventory", "source inventory"),
    ("receipt", "import receipt"),
    ("missing_fact", "observations are missing"),
    ("fact_value", "financial observation differs"),
    ("fact_original", "financial observation differs"),
    ("fact_period", "financial observation differs"),
    ("snapshot", "normalized snapshot"),
    ("warnings", "normalized snapshot"),
    ("source_cache", "original source"),
    ("source_expiry", "original source"),
    ("owner", "ownership conflicts"),
])
def test_readonly_replay_rejects_persisted_evidence_drift(engine, session_factory, import_case, mutation, error):
    plan, result = applied(engine, import_case)
    with session_factory.begin() as session:
        batch = session.get(FinancialImportBatch, result["batch_id"])
        record = batch.summary["imported"][0]
        if mutation == "inventory":
            inventory = deepcopy(batch.source_inventory)
            inventory[0]["sha256"] = "0" * 64
            batch.source_inventory = inventory
        elif mutation == "receipt":
            summary = deepcopy(batch.summary)
            summary["row_changes"]["financial_facts"] += 1
            batch.summary = summary
        elif mutation.startswith("fact_") or mutation == "missing_fact":
            fact = session.scalar(select(FinancialFact))
            if mutation == "missing_fact":
                session.delete(fact)
            elif mutation == "fact_value":
                fact.reported_value += 1
            elif mutation == "fact_original":
                fact.original_source = {**fact.original_source, "value": 999}
            else:
                fact.fiscal_period = "Q1"
        elif mutation in {"snapshot", "warnings"}:
            snapshot = session.get(FinancialSnapshot, record["snapshot_id"])
            if mutation == "snapshot":
                snapshot.normalized_data = {**snapshot.normalized_data, "invented": True}
            else:
                snapshot.warnings = ["changed"]
        elif mutation.startswith("source_"):
            cached = session.get(CacheEntry, record["source_cache_key"])
            if mutation == "source_cache":
                cached.payload = {**cached.payload, "invented": True}
            else:
                cached.expires_at = cached.retrieved_at
        else:
            owner = session.get(Company, record["company_id"])
            owner.cik = "0000789019"
    before = counts(session_factory)
    with pytest.raises(ValueError, match=error):
        verify(engine, plan)
    assert counts(session_factory) == before


def test_readonly_replay_does_not_require_preimport_database_baseline(engine, session_factory, import_case):
    plan, _result = applied(engine, import_case)
    # It verifies the committed request, not a fresh import plan. Unrelated
    # cache additions are neither overwritten nor confused with that request.
    with session_factory.begin() as session:
        now = datetime.now(timezone.utc)
        session.add(CacheEntry(key="unrelated:later", payload={"value": 1}, provider="fixture",
                               retrieved_at=now, expires_at=now))
    before = counts(session_factory)
    assert verify(engine, plan)["receipt"]["already_applied"] is True
    assert counts(session_factory) == before


def legacy_applied(engine, session_factory, import_case):
    raw, spec = import_case
    identity = SecurityRegistryRepository(session_factory).resolve("AAPL")
    repository = FinancialRepository(session_factory)
    company_id = repository.save_company(identity)
    repository.save_financials(company_id, extract_observations(raw), normalize_company_facts(raw, cik=identity["cik"]))
    with session_factory.begin() as session:
        for fact in session.scalars(select(FinancialFact)):
            fact.normalized_metric = None
            fact.original_source = {**fact.original_source, "metric": None}
    plan = preview(engine, spec)
    result = apply_preview(engine, plan, confirmation=confirm(plan))
    return plan, result


def test_readonly_replay_preserves_exact_preexisting_normalization_labels(engine, session_factory, import_case):
    plan, result = legacy_applied(engine, session_factory, import_case)
    before = counts(session_factory)
    replay = verify(engine, plan)
    assert replay["receipt"] == {**result, "already_applied": True}
    assert replay["verification"]["preserved_original_facts"] == 24
    assert replay["verification"]["preserved_label_count"] == 24
    assert replay["verification"]["verified_observations"] == 24
    with session_factory() as session:
        assert all(fact.normalized_metric is None and fact.original_source["metric"] is None
                   for fact in session.scalars(select(FinancialFact)))
    assert counts(session_factory) == before


@pytest.mark.parametrize("mutation", ["normalized_metric", "original_label", "retrieval", "reported_value", "delete"])
def test_readonly_replay_rejects_any_post_import_legacy_fact_mutation(engine, session_factory, import_case, mutation):
    plan, _result = legacy_applied(engine, session_factory, import_case)
    with session_factory.begin() as session:
        fact = session.scalar(select(FinancialFact))
        if mutation == "normalized_metric":
            fact.normalized_metric = "invented"
        elif mutation == "original_label":
            fact.original_source = {**fact.original_source, "metric": "invented"}
        elif mutation == "retrieval":
            fact.retrieved_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        elif mutation == "reported_value":
            fact.reported_value += 1
        else:
            session.delete(fact)
    with pytest.raises(ValueError, match="complete original financial-fact baseline changed"):
        verify(engine, plan)


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Requires the dedicated PostgreSQL *_test database.")
def test_postgres_readonly_verification_connection_rejects_writes():
    url = make_url(os.environ["TEST_DATABASE_URL"])
    if url.get_backend_name() != "postgresql" or not (url.database or "").endswith("_test"):
        pytest.fail("TEST_DATABASE_URL must identify a dedicated PostgreSQL *_test database.")
    database = create_engine(url, connect_args={"connect_timeout": 5})
    try:
        with read_only_connection(database) as connection:
            connection.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
            assert connection.scalar(text("SHOW transaction_read_only")) == "on"
            assert connection.scalar(text("SHOW transaction_isolation")) == "repeatable read"
            # PostgreSQL itself must reject a persistent DDL statement. The
            # failed statement creates nothing; no application table is touched.
            with pytest.raises(DBAPIError) as caught:
                connection.execute(text("CREATE TABLE phase68_forbidden_readonly_probe (id integer)"))
            assert getattr(caught.value.orig, "sqlstate", None) == "25006"
    finally:
        database.dispose()
