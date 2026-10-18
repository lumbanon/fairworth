from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencies import Ticker, company_service
from app.schemas.common import ErrorResponse
from app.schemas.company import CompanyResponse, SearchResponse
from app.schemas.market import PricesResponse
from app.services.security_identity import security_identity, scope_kwargs
from app.schemas.coverage import CoverageResponse

router = APIRouter(prefix="/stocks", tags=["stocks"], responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})


@router.get("/search", response_model=SearchResponse)
async def search_stocks(q: str = Query(min_length=1, max_length=80), limit: int = Query(default=10, ge=1, le=50),
                        offset: int = Query(default=0, ge=0, le=100000), service=Depends(company_service)):
    return await service.search(q, limit, offset)


@router.get("/{ticker}", response_model=CompanyResponse)
async def stock_profile(ticker: Ticker, instrument_id: str | None = Query(default=None, min_length=1, max_length=100), listing_id: str | None = Query(default=None, min_length=1, max_length=100), service=Depends(company_service)):
    return await service.profile(ticker.upper(), **scope_kwargs(instrument_id, listing_id))


@router.get("/{ticker}/prices", response_model=PricesResponse)
async def stock_prices(ticker: Ticker, request: Request, limit: int = Query(default=365, ge=1, le=2000),
                       instrument_id: str | None = Query(default=None, min_length=1, max_length=100), listing_id: str | None = Query(default=None, min_length=1, max_length=100), service=Depends(company_service)):
    return await service.historical_prices(ticker.upper(), min(limit, request.app.state.settings.api_history_limit), **scope_kwargs(instrument_id, listing_id))


@router.get("/{ticker}/resolve")
async def resolve_stock(ticker: Ticker, instrument_id: str | None = Query(default=None, min_length=1, max_length=100), listing_id: str | None = Query(default=None, min_length=1, max_length=100), service=Depends(company_service)):
    company, _ = await service.company_identity(ticker.upper(), **scope_kwargs(instrument_id, listing_id))
    return {"status": "resolved", "identity": {**security_identity(company), "name": company.get("name")}, "candidates": [], "reasons": []}


@router.get("/{ticker}/coverage", response_model=CoverageResponse)
async def stock_coverage(ticker: Ticker, request: Request, instrument_id: str | None = Query(default=None, min_length=1, max_length=100), listing_id: str | None = Query(default=None, min_length=1, max_length=100)):
    return await request.app.state.coverage_service.coverage(ticker.upper(), **scope_kwargs(instrument_id, listing_id))
