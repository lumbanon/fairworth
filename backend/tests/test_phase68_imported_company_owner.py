"""Browsing an imported issuer's second class cannot duplicate financial owners."""
from copy import deepcopy
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.core.config import Settings
from app.core.exceptions import ApiError
from app.models import Company, MarketSnapshot
from app.repositories.financial_repository import FinancialRepository, content_hash
from app.services.cache_service import CachedResult, CacheService
from app.services.company_service import CompanyService
from app.services.financial_import_service import apply_preview, build_preview
from phase66_coverage_helpers import import_captured_listings
from test_phase68_financial_import import CLOCK, confirm, retained_source


@pytest.mark.asyncio
async def test_second_alphabet_class_keeps_one_owner_and_class_scoped_market_data(engine, session_factory, tmp_path, raw_facts):
    _, registry, _ = import_captured_listings(session_factory)
    raw = deepcopy(raw_facts)
    raw["cik"] = 1652044
    source = retained_source(tmp_path, raw, "GOOGL")
    plan = build_preview(engine, [source], as_of=CLOCK, sec_cache_ttl_seconds=21600)
    applied = apply_preview(engine, plan, confirmation=confirm(plan))
    company_id = applied["imported"][0]["company_id"]
    with session_factory() as session:
        owner = session.get(Company, company_id)
        original = content_hash({column.name: getattr(owner, column.name) for column in Company.__table__.columns})
    class Market:
        name = "fixture-market"
        async def profile(self, ticker):
            return {"description": f"Selected {ticker} profile", "currency": "USD"}
        async def quote(self, ticker):
            return {"price": 101 if ticker == "GOOG" else 202, "currency": "USD", "exchange": "NASDAQ",
                "price_timestamp": datetime.now(UTC).isoformat(), "market_cap": 1010 if ticker == "GOOG" else 2020,
                "shares_outstanding": 10, "warnings": []}
    repository = FinancialRepository(session_factory)
    service = CompanyService(None, Market(), CacheService(session_factory), repository, Settings())
    async def selected(ticker, **_scope):
        identity = {**registry.resolve(ticker), "has_multiple_share_classes": True}
        return identity, CachedResult(identity, "fresh", datetime.now(UTC), [])
    service.company_identity = selected
    alternate = await service.profile("GOOG")
    assert alternate["company"]["ticker"] == "GOOG" and alternate["market"]["price"] == 101
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Company)) == 1
        assert session.scalar(select(func.count()).select_from(MarketSnapshot)) == 0
    canonical = await service.profile("GOOGL")
    assert canonical["market"]["price"] == 202
    with session_factory() as session:
        owner = session.get(Company, company_id)
        assert content_hash({column.name: getattr(owner, column.name) for column in Company.__table__.columns}) == original
        observations = session.scalars(select(MarketSnapshot)).all()
        assert len(observations) == 1
        assert observations[0].original_source["security_identity"]["ticker"] == "GOOGL"
    identity = registry.resolve("GOOG")
    assert repository.imported_dataset(identity["issuer_id"], identity["cik"])["company_id"] == company_id


def test_market_repository_rejects_explicit_other_class_identity(engine, session_factory, tmp_path, raw_facts):
    _, registry, _ = import_captured_listings(session_factory)
    raw = deepcopy(raw_facts)
    raw["cik"] = 1652044
    source = retained_source(tmp_path, raw, "GOOGL")
    plan = build_preview(engine, [source], as_of=CLOCK, sec_cache_ttl_seconds=21600)
    result = apply_preview(engine, plan, confirmation=confirm(plan))
    with pytest.raises(ApiError, match="class-specific market observation"):
        FinancialRepository(session_factory).save_market(result["imported"][0]["company_id"], {
            "price": 101, "currency": "USD", "provider": "fixture-market", "security_identity": registry.resolve("GOOG")})
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(MarketSnapshot)) == 0
