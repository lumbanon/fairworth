from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencies import Ticker, company_service
from app.schemas.common import ErrorResponse
from app.schemas.company import CompanyResponse, SearchResponse
from app.schemas.market import PricesResponse

router = APIRouter(prefix="/stocks", tags=["stocks"], responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})


@router.get("/search", response_model=SearchResponse)
async def search_stocks(q: str = Query(min_length=1, max_length=80), limit: int = Query(default=10, ge=1, le=50),
                        service=Depends(company_service)):
    return await service.search(q, limit)


@router.get("/{ticker}", response_model=CompanyResponse)
async def stock_profile(ticker: Ticker, service=Depends(company_service)):
    return await service.profile(ticker.upper())


@router.get("/{ticker}/prices", response_model=PricesResponse)
async def stock_prices(ticker: Ticker, request: Request, limit: int = Query(default=365, ge=1, le=2000),
                       service=Depends(company_service)):
    return await service.historical_prices(ticker.upper(), min(limit, request.app.state.settings.api_history_limit))
