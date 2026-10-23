"""Native PostgreSQL apply/rollback against only the guarded disposable DB."""
from copy import deepcopy
import os

from alembic import command
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from app.core.database import build_session_factory
from app.models import Company
from app.registry.repository import SecurityRegistryRepository
from app.repositories.financial_repository import FinancialRepository
from app.services.financial_import_service import apply_preview, build_preview
from phase66_coverage_helpers import import_captured_listings
from test_phase66_financial_identity import migration_config
from test_phase68_financial_import import CLOCK, confirm, counts, retained_source


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="Requires the existing dedicated PostgreSQL *_test database.")
def test_postgres_import_atomicity_preservation_and_audit_migration(tmp_path, raw_facts):
    url = make_url(TEST_DATABASE_URL)
    if url.get_backend_name() != "postgresql" or not (url.database or "").endswith("_test"):
        pytest.fail("TEST_DATABASE_URL must identify a dedicated PostgreSQL *_test database.")
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    with engine.connect() as connection:
        assert set(inspect(connection).get_table_names()) <= {"alembic_version"}
        connection.rollback()
        config = migration_config(connection)
        command.upgrade(config, "0004_financial_issuer_ownership")
        connection.commit()
    factory = build_session_factory(engine)
    try:
        import_captured_listings(factory)
        other = SecurityRegistryRepository(factory).resolve("MSFT")
        original_id = FinancialRepository(factory).save_company(other)
        with engine.connect() as connection:
            before = connection.execute(text("SELECT * FROM companies ORDER BY id")).all()
            connection.rollback()
            config = migration_config(connection)
            command.upgrade(config, "head")
            connection.commit()
            assert connection.execute(text("SELECT * FROM companies ORDER BY id")).all() == before
            command.check(config)
            connection.rollback()
        raw = deepcopy(raw_facts)
        raw["cik"] = 320193
        spec = retained_source(tmp_path, raw)
        plan = build_preview(engine, [spec], as_of=CLOCK, sec_cache_ttl_seconds=21600)
        original_counts = counts(factory)
        def fail(_session, _report):
            raise RuntimeError("PostgreSQL rollback sentinel")
        with pytest.raises(RuntimeError, match="sentinel"):
            apply_preview(engine, plan, confirmation=confirm(plan), fault_hook=fail)
        assert counts(factory) == original_counts
        result = apply_preview(engine, plan, confirmation=confirm(plan))
        assert result["row_changes"]["financial_facts"] == 24
        assert apply_preview(engine, plan, confirmation=confirm(plan))["already_applied"]
        with factory() as session:
            assert session.get(Company, original_id).name == other["name"]
        with engine.connect() as connection:
            config = migration_config(connection)
            with pytest.raises(RuntimeError, match="durable provenance"):
                command.downgrade(config, "0004_financial_issuer_ownership")
            connection.rollback()
    finally:
        # Explicit disposable test DB teardown; never an application connection.
        with engine.begin() as connection:
            if inspect(connection).has_table("financial_import_batches"):
                connection.execute(text("DELETE FROM financial_import_batches"))
        with engine.connect() as connection:
            config = migration_config(connection)
            command.downgrade(config, "base")
            connection.commit()
            assert set(inspect(connection).get_table_names()) <= {"alembic_version"}
        engine.dispose()
