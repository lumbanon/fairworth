"""Versioned normalization preserves earlier snapshots and immutable source facts."""

from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models import FinancialFact, FinancialSnapshot
from app.repositories.financial_repository import FinancialRepository, content_hash
from app.services.cache_service import CachedResult, CacheService
from app.services.financial_service import FinancialService
from app.services.normalization import NORMALIZATION_VERSION, extract_observations, normalize_company_facts
from test_normalization import observation, payload


def historical_source():
    """Explicit synthetic v3 history; its unsafe scope remains historical only."""
    raw = payload({
        "Revenues": ("USD", [observation(1000)]),
        "DebtCurrent": ("USD", [observation(40, None)]),
        "LongTermDebtCurrent": ("USD", [observation(10, None)]),
        "LongTermDebtNoncurrent": ("USD", [observation(80, None)]),
        "ShareBasedCompensation": ("USD", [observation(5)]),
    })
    old_observations = extract_observations(raw)
    for row in old_observations:
        if row["concept"] == "DebtCurrent":
            row["metric"] = "short_term_debt"
        elif row["concept"] == "ShareBasedCompensation":
            row["metric"] = None
    old_snapshot = {
        "normalization_version": 3,
        "annual": [{
            "fiscal_year": 2024, "fiscal_period": "FY",
            "start_date": "2024-01-01", "end_date": "2024-12-31", "currency": "USD",
            "metrics": {"revenue": 1000, "short_term_debt": 40, "long_term_debt": 80, "total_debt": 120},
            "provenance": {}, "warnings": [],
        }],
        "quarterly": [], "currency": "USD", "status": "partial", "warnings": [], "source_references": [],
    }
    return raw, old_observations, old_snapshot


def fact_state(session_factory, company_id):
    with session_factory() as session:
        return {
            row.observation_key: {
                "id": row.id, "normalized_metric": row.normalized_metric,
                "reported_value": row.reported_value, "unit": row.unit,
                "original_source": deepcopy(row.original_source), "retrieved_at": row.retrieved_at,
                "accession_number": row.accession_number, "filing_date": row.filing_date,
                "period_start": row.period_start, "period_end": row.period_end,
            }
            for row in session.scalars(select(FinancialFact).where(FinancialFact.company_id == company_id))
        }


def normalization_history_contract(session_factory):
    """Reusable for the dedicated PostgreSQL migration/persistence contract."""
    raw, old_observations, old_snapshot = historical_source()
    repository = FinancialRepository(session_factory)
    company_id = repository.save_company({"ticker": "P6FIXTURE", "name": "Synthetic normalization history", "cik": "0000000001"})
    repository.save_financials(company_id, old_observations, old_snapshot)
    originals = fact_state(session_factory, company_id)
    updated = normalize_company_facts(raw, cik="0000000001")
    repository.save_financials(company_id, extract_observations(raw), updated)
    repository.save_financials(company_id, extract_observations(raw), updated)
    assert fact_state(session_factory, company_id) == originals
    assert len(originals) == 5
    with session_factory() as session:
        snapshots = list(session.scalars(select(FinancialSnapshot).where(FinancialSnapshot.company_id == company_id)))
        assert len(snapshots) == 2
        indexed = {row.normalized_data["normalization_version"]: row for row in snapshots}
        assert indexed[3].normalized_data == old_snapshot
        assert indexed[3].content_hash == content_hash(old_snapshot)
        assert indexed[NORMALIZATION_VERSION].normalized_data == updated
        assert indexed[NORMALIZATION_VERSION].content_hash != indexed[3].content_hash
    assert old_snapshot["annual"][0]["metrics"]["total_debt"] == 120
    assert updated["annual"][0]["metrics"]["total_debt"] is None
    assert updated["annual"][0]["metrics"]["current_debt_including_lease_obligations"] == 40
    assert updated["annual"][0]["metrics"]["stock_based_compensation"] == 5


def test_new_normalization_snapshot_is_immutable_and_raw_facts_remain_idempotent(session_factory):
    normalization_history_contract(session_factory)


@pytest.mark.asyncio
async def test_versioned_cache_recalculates_from_same_raw_source_without_provider_refresh(session_factory):
    raw, old_observations, old_snapshot = historical_source()
    cache = CacheService(session_factory)
    repository = FinancialRepository(session_factory)
    company = {"ticker": "P6CACHE", "name": "Synthetic cached history", "cik": "0000000001"}
    company_id = repository.save_company(company)
    repository.save_financials(company_id, old_observations, old_snapshot)
    originals = fact_state(session_factory, company_id)
    original_time = datetime(2025, 2, 15, 12, tzinfo=UTC)
    raw_key = "sec:facts:0000000001"
    old_key = "sec:financials:0000000001:P6CACHE:v3"
    new_key = f"sec:financials:0000000001:P6CACHE:v{NORMALIZATION_VERSION}"
    cache._write(raw_key, raw, 3600, "sec-edgar")
    cache._write(old_key, old_snapshot, 3600, "sec-edgar", original_time)

    class Identity:
        async def company_identity(self, ticker):
            assert ticker == company["ticker"]
            return company, CachedResult(company, "fresh", original_time, [])

    class NoProviderRefresh:
        async def facts(self, cik):
            raise AssertionError("A normalization version change must reuse the fresh raw cache.")

    service = FinancialService(Identity(), NoProviderRefresh(), cache, repository,
                               SimpleNamespace(sec_cache_ttl_seconds=3600))
    first = await service.dataset(company["ticker"])
    second = await service.dataset(company["ticker"])
    assert first[1].payload == second[1].payload
    assert first[1].payload["normalization_version"] == NORMALIZATION_VERSION
    assert cache._read(old_key).payload == old_snapshot
    assert cache._read(new_key).payload == first[1].payload
    assert cache._read(raw_key).payload == raw
    assert fact_state(session_factory, company_id) == originals
    with session_factory() as session:
        snapshots = list(session.scalars(select(FinancialSnapshot).where(FinancialSnapshot.company_id == company_id)))
        assert len(snapshots) == 2
