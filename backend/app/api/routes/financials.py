from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.services.security_identity import scope_kwargs
from app.api.dependencies import Ticker, financial_service
from app.schemas.common import ErrorResponse
from app.schemas.financials import DataStatusResponse, FinancialResponse, MetricsResponse

router = APIRouter(prefix="/stocks", tags=["financials"], responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})


@router.get("/{ticker}/financials", response_model=FinancialResponse)
async def financial_statements(ticker: Ticker, period: Literal["annual", "quarterly"] = "annual",
                               limit: int = Query(default=10, ge=1, le=20), instrument_id: str | None = Query(default=None, min_length=1, max_length=100), listing_id: str | None = Query(default=None, min_length=1, max_length=100), service=Depends(financial_service)):
    return await service.statements(ticker.upper(), period, limit, **scope_kwargs(instrument_id, listing_id))


@router.get("/{ticker}/metrics", response_model=MetricsResponse)
async def financial_metrics(ticker: Ticker, period: Literal["annual", "quarterly"] = "annual",
                            limit: int = Query(default=10, ge=1, le=20), instrument_id: str | None = Query(default=None, min_length=1, max_length=100), listing_id: str | None = Query(default=None, min_length=1, max_length=100), service=Depends(financial_service)):
    return await service.metrics(ticker.upper(), period, limit, **scope_kwargs(instrument_id, listing_id))


@router.get("/{ticker}/data-status", response_model=DataStatusResponse)
async def stock_data_status(ticker: Ticker, instrument_id: str | None = Query(default=None, min_length=1, max_length=100), listing_id: str | None = Query(default=None, min_length=1, max_length=100), service=Depends(financial_service)):
    return await service.data_status(ticker.upper(), **scope_kwargs(instrument_id, listing_id))
