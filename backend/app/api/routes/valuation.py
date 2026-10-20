"""Transient Provider valuations with explicit sources and bounded requests."""
from fastapi import APIRouter, Depends, Request, Query

from app.services.security_identity import scope_kwargs
from app.api.dependencies import Ticker
from app.core.exceptions import ApiError
from app.schemas.common import ErrorResponse
from app.valuation.schemas import EligibilityResponse, SensitivityResponse, ValuationRequest, ValuationResponse

router = APIRouter(prefix="/stocks", tags=["valuation"], responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})


def valuation_service(request: Request):
    return request.app.state.valuation_service


@router.get("/{ticker}/valuation/defaults", response_model=ValuationResponse)
async def defaults(ticker: Ticker, instrument_id: str | None = Query(default=None, min_length=1, max_length=100), listing_id: str | None = Query(default=None, min_length=1, max_length=100), service=Depends(valuation_service)):
    return await service.calculate(ticker.upper(), **scope_kwargs(instrument_id, listing_id))


@router.post("/{ticker}/valuation/calculate", response_model=ValuationResponse)
async def calculate(ticker: Ticker, body: ValuationRequest, instrument_id: str | None = Query(default=None, min_length=1, max_length=100), listing_id: str | None = Query(default=None, min_length=1, max_length=100), service=Depends(valuation_service)):
    return await service.calculate(ticker.upper(), body, **scope_kwargs(instrument_id, listing_id))


@router.post("/{ticker}/valuation/scenarios", response_model=ValuationResponse)
async def scenarios(ticker: Ticker, body: ValuationRequest, instrument_id: str | None = Query(default=None, min_length=1, max_length=100), listing_id: str | None = Query(default=None, min_length=1, max_length=100), service=Depends(valuation_service)):
    return await service.calculate(ticker.upper(), body, **scope_kwargs(instrument_id, listing_id))


@router.post("/{ticker}/valuation/sensitivity", response_model=SensitivityResponse)
async def sensitivity(ticker: Ticker, body: ValuationRequest, instrument_id: str | None = Query(default=None, min_length=1, max_length=100), listing_id: str | None = Query(default=None, min_length=1, max_length=100), service=Depends(valuation_service)):
    if body.sensitivity is None:
        raise ApiError("missing_sensitivity", "A bounded sensitivity specification is required.", 422)
    return (await service.calculate(ticker.upper(), body, **scope_kwargs(instrument_id, listing_id)))["sensitivity"]


@router.get("/{ticker}/valuation/eligibility", response_model=EligibilityResponse)
async def model_eligibility(ticker: Ticker, instrument_id: str | None = Query(default=None, min_length=1, max_length=100), listing_id: str | None = Query(default=None, min_length=1, max_length=100), service=Depends(valuation_service)):
    result = await service.calculate(ticker.upper(), **scope_kwargs(instrument_id, listing_id))
    return {"company": result["company"], "engine_version": result["engine_version"],
            "models": [{"id": model["id"], **model["eligibility"]} for model in result["scenarios"]["base"]["models"]]}


@router.get("/{ticker}/valuation/explain", response_model=ValuationResponse)
async def explain(ticker: Ticker, instrument_id: str | None = Query(default=None, min_length=1, max_length=100), listing_id: str | None = Query(default=None, min_length=1, max_length=100), service=Depends(valuation_service)):
    return await service.calculate(ticker.upper(), **scope_kwargs(instrument_id, listing_id))
