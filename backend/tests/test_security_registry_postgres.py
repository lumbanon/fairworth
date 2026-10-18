"""Opt-in PostgreSQL-only registry verification on an empty *_test database."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import threading
import time
from types import SimpleNamespace

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from app.core.database import build_session_factory
from app.registry.repository import SecurityRegistryRepository
from app.registry.service import SecurityRegistryService
from app.repositories.financial_repository import FinancialRepository
from app.services.cache_service import CacheService
from test_security_registry import PROVENANCE, record


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


def _index_names(plan):
    names = [plan["Index Name"]] if "Index Name" in plan else []
    return names + [name for child in plan.get("Plans", []) for name in _index_names(child)]


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="Requires a dedicated empty PostgreSQL *_test database.")
def test_postgres_registry_migration_persistence_search_plans_and_concurrency():
    url = make_url(TEST_DATABASE_URL)
    if url.get_backend_name() != "postgresql" or not (url.database or "").endswith("_test"):
        pytest.fail("TEST_DATABASE_URL must be a dedicated PostgreSQL database ending in _test.")
    engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with engine.connect() as connection:
        assert set(inspect(connection).get_table_names()) <= {"alembic_version"}, "Dedicated integration database must start empty."
        connection.rollback()
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        connection.commit()
    try:
        factory = build_session_factory(engine)
        repository = SecurityRegistryRepository(factory)
        rows = [record(f"ZS{index:05d}", cik=str(index + 1), name=f"Synthetic Sector{index % 20} Issuer {index:05d}")
                for index in range(10000)]
        started = time.perf_counter()
        imported = repository.import_snapshot(rows, PROVENANCE)
        import_seconds = time.perf_counter() - started
        assert repository.import_snapshot(rows, PROVENANCE)["changed"] is False
        assert repository.resolve("ZS05000")["cik"] == "0000005001"
        with engine.begin() as connection:
            connection.execute(text("ANALYZE security_listings"))
            connection.execute(text("ANALYZE security_aliases"))
            ticker_plan = connection.execute(text("EXPLAIN (FORMAT JSON) SELECT id FROM security_listings WHERE ticker LIKE 'ZS050%'" )).scalar_one()
            alias_plan = connection.execute(text("EXPLAIN (FORMAT JSON) SELECT listing_id FROM security_aliases WHERE normalized_value LIKE 'SECTOR12%'" )).scalar_one()
            assert "ix_registry_ticker_prefix" in _index_names(ticker_plan[0]["Plan"])
            assert "ix_registry_alias_prefix" in _index_names(alias_plan[0]["Plan"])
        timings = {}
        for name, query, offset in (("ticker", "ZS05000", 0), ("name", "sector12", 0), ("prefix", "ZS05", 0), ("page", "ZS05", 30)):
            started = time.perf_counter()
            result = repository.search(query, 10, offset)
            timings[name] = time.perf_counter() - started
            assert result["results"] and len(result["results"]) <= 10
        service = SecurityRegistryService(factory, SimpleNamespace(registry_bootstrap_enabled=False))
        async def parallel_searches():
            return await asyncio.gather(*(service.search(query, 10) for query in ["ZS05000", "sector12", "ZS05"] * 8))
        started = time.perf_counter()
        responses = asyncio.run(parallel_searches())
        timings["24_concurrent_searches"] = time.perf_counter() - started
        assert len(responses) == 24 and all(result["results"] for result in responses)

        # Independent event loops model separate application workers sharing SQL.
        calls, counter_lock, entered = [], threading.Lock(), threading.Event()
        def worker(index):
            async def run():
                cache = CacheService(factory, lease_seconds=1, wait_seconds=3, poll_seconds=.01)
                async def load():
                    with counter_lock:
                        calls.append(index)
                    entered.set()
                    await asyncio.sleep(.12)
                    return {"observation": "one public synthetic snapshot"}
                return await cache.get_or_load("postgres-worker-coalescing", 300, "synthetic", load)
            return asyncio.run(run())
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(worker, 0)
            assert entered.wait(3)
            second = executor.submit(worker, 1)
            assert first.result(timeout=5).payload == second.result(timeout=5).payload
        assert len(calls) == 1
        from cache_lease_postgres_helpers import renewal_sweep_race
        renewal_sweep_race(factory, engine)

        financial = FinancialRepository(factory)
        company_id = financial.save_company({"ticker": "ZZHIST", "name": "Synthetic historical preservation", "cik": "0000900000"})
        historical = {"annual": [], "quarterly": [], "warnings": [], "source_references": []}
        financial.save_financials(company_id, [], historical)
        with engine.connect() as connection:
            config.attributes["connection"] = connection
            command.check(config)
            command.downgrade(config, "0001_financial_data")
            connection.commit()
            assert "security_listings" not in inspect(connection).get_table_names()
            assert connection.execute(text("SELECT count(*) FROM financial_snapshots")).scalar_one() == 1
            connection.rollback()
            command.upgrade(config, "head")
            connection.commit()
            command.check(config)
        assert financial.latest_snapshot(company_id).normalized_data == historical
        print(json.dumps({"synthetic_registry_rows": 10000, "import_seconds": import_seconds,
                          "search_seconds": timings, "index_plans": ["ix_registry_ticker_prefix", "ix_registry_alias_prefix"],
                          "cross_worker_loader_calls": len(calls)}, sort_keys=True))
    finally:
        # Only this independently checked disposable test database is changed.
        with engine.connect() as connection:
            config.attributes["connection"] = connection
            command.downgrade(config, "base")
            connection.commit()
            assert set(inspect(connection).get_table_names()) <= {"alembic_version"}
        engine.dispose()
