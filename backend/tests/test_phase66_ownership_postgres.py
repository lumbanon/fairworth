"""Opt-in native ALTER proof on the existing dedicated PostgreSQL *_test DB."""
import os

from alembic import command
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from app.core.database import build_session_factory
from app.repositories.financial_repository import FinancialRepository
from test_phase66_financial_identity import legacy_company, migration_config

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="Requires the dedicated empty PostgreSQL *_test database.")
def test_postgres_issuer_upgrade_preserves_history_and_guarded_rollback():
    url = make_url(TEST_DATABASE_URL)
    if url.get_backend_name() != "postgresql" or not (url.database or "").endswith("_test"):
        pytest.fail("TEST_DATABASE_URL must name a dedicated PostgreSQL *_test database.")
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    with engine.connect() as connection:
        assert set(inspect(connection).get_table_names()) <= {"alembic_version"}, "Dedicated database must start empty."
        connection.rollback()
        config = migration_config(connection)
        command.upgrade(config, "0003_listing_observations")
        legacy_company(connection)
        connection.execute(text("INSERT INTO security_issuers(id,source_key,cik,name,source_refs,business_category,classification_evidence,updated_at) VALUES('existing-issuer','synthetic:existing','0000000001','Synthetic existing','[]','unknown','{}','2026-10-18')"))
        connection.exec_driver_sql("INSERT INTO financial_facts(id,company_id,observation_key,concept,reported_value,unit,original_source,retrieved_at) VALUES(71,51,'synthetic-observation','Revenue',12.123456789,'USD','{\"unchanged\":true}','2026-10-18')")
        connection.exec_driver_sql("INSERT INTO market_snapshots(id,company_id,content_hash,provider,original_source,retrieved_at) VALUES(91,51,'synthetic-market','synthetic','{\"unchanged\":true}','2026-10-18')")
        connection.commit()
    try:
        with engine.connect() as connection:
            config = migration_config(connection)
            before = {table: connection.execute(text("SELECT * FROM " + table + " ORDER BY id")).all()
                      for table in ("financial_facts", "financial_snapshots", "market_snapshots")}
            connection.rollback()
            command.upgrade(config, "head")
            connection.commit()
            assert connection.execute(text("SELECT issuer_id FROM companies WHERE id=51")).scalar_one() == "existing-issuer"
            for table, rows in before.items():
                assert connection.execute(text("SELECT * FROM " + table + " ORDER BY id")).all() == rows
            indexes = {row["name"]: row for row in inspect(connection).get_indexes("companies")}
            assert not indexes["ix_companies_ticker"]["unique"]
            command.check(config)
            connection.rollback()
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO security_issuers(id,source_key,cik,name,source_refs,business_category,classification_evidence,updated_at) VALUES('second-issuer','synthetic:second','0000000002','Synthetic second','[]','unknown','{}','2026-10-18')"))
        replacement = FinancialRepository(build_session_factory(engine)).save_company(
            {"ticker": "SYN", "name": "Synthetic second", "cik": "0000000002", "issuer_id": "second-issuer"})
        with engine.connect() as connection:
            config = migration_config(connection)
            with pytest.raises(RuntimeError, match="reused tickers"):
                command.downgrade(config, "0003_listing_observations")
            connection.rollback()
            assert connection.execute(text("SELECT count(*) FROM companies WHERE ticker='SYN'")).scalar_one() == 2
            connection.rollback()
        # Remove only the duplicate created by this test so the lossless legacy
        # rollback can be demonstrated; no application database is involved.
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM companies WHERE id=:id"), {"id": replacement})
        with engine.connect() as connection:
            config = migration_config(connection)
            command.downgrade(config, "0003_listing_observations")
            connection.commit()
            for table, rows in before.items():
                assert connection.execute(text("SELECT * FROM " + table + " ORDER BY id")).all() == rows
            connection.rollback()
            command.upgrade(config, "head")
            connection.commit()
            assert connection.execute(text("SELECT issuer_id FROM companies WHERE id=51")).scalar_one() == "existing-issuer"
            command.check(config)
            connection.rollback()
    finally:
        with engine.connect() as connection:
            config = migration_config(connection)
            command.downgrade(config, "base")
            connection.commit()
            assert set(inspect(connection).get_table_names()) <= {"alembic_version"}
        engine.dispose()
