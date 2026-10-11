from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, inspect, select

from app.models import Company, FinancialFact, FinancialSnapshot, MarketSnapshot
from app.repositories.financial_repository import FinancialRepository


def test_company_creation_fact_provenance_and_duplicate_prevention(session_factory):
    repository = FinancialRepository(session_factory)
    company = {"ticker": "MSFT", "name": "Fixture Company", "cik": "0000000001", "currency": "USD"}
    company_id = repository.save_company(company)
    assert repository.save_company(company) == company_id
    observations = [{"concept": "Revenue", "taxonomy": "us-gaap", "metric": "revenue", "value": 100,
                     "unit": "USD", "start": "2024-01-01", "end": "2024-12-31", "fy": 2024, "fp": "FY",
                     "filed": "2025-02-01", "form": "10-K", "accn": "0000000001-25-000001", "source": "sec"},
                    {"concept": "UnmappedConcept", "metric": None, "value": -50, "unit": "USD",
                     "end": "2024-12-31", "source": "sec"}]
    normalized = {"annual": [{"end_date": "2024-12-31", "metrics": {"revenue": 100}}], "quarterly": [],
                  "warnings": [], "source_references": [{"provider": "sec", "accn": "0000000001-25-000001"}]}
    repository.save_financials(company_id, observations, normalized)
    repository.save_financials(company_id, observations, normalized)
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Company)) == 1
        assert session.scalar(select(func.count()).select_from(FinancialFact)) == 2
        assert session.scalar(select(func.count()).select_from(FinancialSnapshot)) == 1
        fact = session.scalar(select(FinancialFact).where(FinancialFact.concept == "Revenue"))
        assert fact.original_source["taxonomy"] == "us-gaap"
        assert fact.accession_number == "0000000001-25-000001"
        assert str(fact.period_start) == "2024-01-01"
    assert repository.latest_snapshot(company_id).normalized_data == normalized


def test_restatement_and_new_snapshots_preserve_history(session_factory):
    repository = FinancialRepository(session_factory)
    company_id = repository.save_company({"ticker": "MSFT", "name": "Fixture Company", "cik": "0000000001"})
    original = {"concept": "NetIncomeLoss", "value": -50, "metric": "net_income", "unit": "USD", "end": "2024-12-31", "accn": "original"}
    restated = {**original, "value": -45, "accn": "amended", "form": "10-K/A"}
    for observation in (original, restated):
        repository.save_financials(company_id, [observation], {"annual": [{"end_date": "2024-12-31", "metrics": {"net_income": observation["value"]}}]})
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(FinancialFact)) == 2
        assert session.scalar(select(func.count()).select_from(FinancialSnapshot)) == 2


def test_market_snapshot_deduplicates_same_observation(session_factory):
    repository = FinancialRepository(session_factory)
    company_id = repository.save_company({"ticker": "MSFT", "name": "Fixture Company", "cik": "0000000001"})
    quote = {"price": 100, "price_timestamp": "2025-01-01T20:00:00Z", "currency": "USD", "provider": "fixture",
             "retrieved_at": "2025-01-01T20:05:00Z"}
    repository.save_market(company_id, quote)
    repository.save_market(company_id, {**quote, "retrieved_at": "2025-01-02T00:00:00Z"})
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(MarketSnapshot)) == 1
        assert session.scalar(select(MarketSnapshot)).original_source["price"] == 100
        from app.core.database import as_utc
        assert as_utc(session.scalar(select(MarketSnapshot)).retrieved_at).isoformat() == "2025-01-01T20:05:00+00:00"


def test_identity_only_update_preserves_enriched_profile_metadata(session_factory):
    repository = FinancialRepository(session_factory)
    profile = {"ticker": "MSFT", "name": "Fixture Company", "cik": "0000000001", "exchange": "NASDAQ",
               "sector": "Technology", "industry": "Software", "description": "Enriched profile", "currency": "USD"}
    company_id = repository.save_company(profile)
    repository.save_company({"ticker": "MSFT", "name": "Fixture Company", "cik": "0000000001",
                             "exchange": None, "sector": None, "industry": None, "description": None, "currency": None})
    with session_factory() as session:
        company = session.get(Company, company_id)
        for field in ("exchange", "sector", "industry", "description", "currency"):
            assert getattr(company, field) == profile[field]


def test_alembic_upgrade_and_downgrade_roundtrip(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.sqlite'}")
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        expected = {"companies", "financial_facts", "financial_snapshots", "market_snapshots", "cache_entries"}
        assert expected.issubset(inspect(connection).get_table_names())
        assert {column["name"] for column in inspect(connection).get_columns("financial_facts")} >= {"accession_number", "original_source", "reported_value"}
        command.check(config)
        command.downgrade(config, "base")
        assert expected.isdisjoint(inspect(connection).get_table_names())
    engine.dispose()
