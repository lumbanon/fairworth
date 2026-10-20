"""Opt-in PostgreSQL integration against a dedicated disposable *_test database."""
import asyncio
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url

from app.core.database import build_session_factory
from test_cache import test_cache_reuses_fresh_data_and_marks_failure_fallback_stale as cache_contract
from test_database import (test_company_creation_fact_provenance_and_duplicate_prevention as persistence_contract,
                           test_market_snapshot_deduplicates_same_observation as market_contract,
                           test_restatement_and_new_snapshots_preserve_history as history_contract)
from test_phase6_persistence import normalization_history_contract

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="Set TEST_DATABASE_URL to a dedicated disposable PostgreSQL *_test database.")
def test_postgres_migration_persistence_cache_and_downgrade():
    url = make_url(TEST_DATABASE_URL)
    if url.get_backend_name() != "postgresql" or not (url.database or "").endswith("_test"):
        pytest.fail("TEST_DATABASE_URL must identify a dedicated PostgreSQL database ending in _test.")
    engine = create_engine(url, pool_pre_ping=True)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with engine.connect() as connection:
        assert set(inspect(connection).get_table_names()) <= {"alembic_version"}, "Integration database must start empty."
        connection.rollback()
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        connection.commit()
    try:
        session_factory = build_session_factory(engine)
        persistence_contract(session_factory)
        market_contract(session_factory)
        # A separate ticker avoids assumptions about prior rows in reused helper.
        with session_factory.begin() as session:
            from app.models import FinancialFact, FinancialSnapshot
            session.query(FinancialFact).delete()
            session.query(FinancialSnapshot).delete()
        history_contract(session_factory)
        asyncio.run(cache_contract(session_factory))
        normalization_history_contract(session_factory)
        with engine.connect() as connection:
            config.attributes["connection"] = connection
            command.check(config)
            columns = {column["name"]: column["type"] for column in inspect(connection).get_columns("financial_facts")}
            assert columns["original_source"].__class__.__name__ == "JSONB"
            assert columns["reported_value"].__class__.__name__ == "NUMERIC"
    finally:
        with engine.connect() as connection:
            config.attributes["connection"] = connection
            command.downgrade(config, "base")
            connection.commit()
            assert set(inspect(connection).get_table_names()) <= {"alembic_version"}
        engine.dispose()
