import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from app.api.routes import financials, health, stocks, valuation
from app.core.config import get_settings
from app.core.database import build_engine, build_session_factory
from app.core.exceptions import ApiError
from app.core.logging import configure_logging
from app.providers.base import ProviderError
from app.providers.market_data import DisabledMarketDataProvider, FmpMarketDataProvider
from app.providers.sec_edgar import SecEdgarProvider
from app.providers.treasury import TreasuryYieldProvider
from app.repositories.financial_repository import FinancialRepository
from app.schemas.common import ErrorDetail, ErrorResponse
from app.services.cache_service import CacheService
from app.services.company_service import CompanyService
from app.services.financial_service import FinancialService
from app.services.valuation_service import ValuationService
from app.services.automatic_inputs_service import AutomaticInputsService


def error_response(code, message, status_code, details=None):
    payload = ErrorResponse(error=ErrorDetail(code=code, message=message, details=details)).model_dump(mode="json", exclude_none=True)
    return JSONResponse(payload, status_code=status_code)


def create_app(settings=None, engine=None, providers=None):
    configure_logging()
    settings = settings or get_settings()
    engine = engine if engine is not None else build_engine(settings.database_url)
    session_factory = build_session_factory(engine)

    @asynccontextmanager
    async def lifespan(application):
        async with httpx.AsyncClient(timeout=settings.provider_timeout_seconds,
                                     limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
                                     follow_redirects=False) as client:
            if providers:
                sec, market = providers
            else:
                sec = SecEdgarProvider(client, user_agent=settings.sec_user_agent,
                                       min_interval=settings.sec_min_interval_seconds,
                                       retries=settings.provider_retries, timeout=settings.provider_timeout_seconds,
                                       ticker_cache_seconds=settings.company_cache_ttl_seconds)
                market = (FmpMarketDataProvider(client, api_key=settings.fmp_api_key,
                                                retries=settings.provider_retries, timeout=settings.provider_timeout_seconds,
                                                stale_price_seconds=settings.market_max_age_seconds)
                          if settings.market_data_provider == "fmp" and settings.fmp_api_key
                          else DisabledMarketDataProvider(client))
            cache = CacheService(session_factory)
            repository = FinancialRepository(session_factory)
            company_service = CompanyService(sec, market, cache, repository, settings)
            application.state.company_service = company_service
            application.state.financial_service = FinancialService(company_service, sec, cache, repository, settings)
            treasury = TreasuryYieldProvider(client, retries=settings.provider_retries, timeout=settings.provider_timeout_seconds) if not providers and settings.valuation_treasury_enabled else None
            automatic = AutomaticInputsService(company_service, application.state.financial_service, settings, treasury) if settings.valuation_automatic_inputs_enabled else None
            application.state.valuation_service = ValuationService(company_service, application.state.financial_service, settings, automatic)
            yield
        engine.dispose()

    application = FastAPI(title="Fairworth Financial Data and Valuation API", version="0.4.5", lifespan=lifespan,
                          description="Sourced financial data and transparent, bounded Python valuations for Provider mode.",
                          responses={422: {"model": ErrorResponse}, 500: {"model": ErrorResponse},
                                     502: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})
    application.state.settings = settings
    application.state.session_factory = session_factory
    application.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=False,
                               allow_methods=["GET", "POST"], allow_headers=["Accept", "Content-Type"])
    application.include_router(health.router, prefix="/api")
    application.include_router(stocks.router, prefix="/api")
    application.include_router(financials.router, prefix="/api")
    application.include_router(valuation.router, prefix="/api")

    @application.exception_handler(ProviderError)
    async def provider_error_handler(_request: Request, error: ProviderError):
        return error_response(error.code, error.message, error.status_code)

    @application.exception_handler(ApiError)
    async def api_error_handler(_request: Request, error: ApiError):
        return error_response(error.code, error.message, error.status_code, error.details)

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(_request: Request, error: RequestValidationError):
        details = [{"field": ".".join(str(part) for part in issue["loc"]), "message": issue["msg"], "type": issue["type"]}
                   for issue in error.errors()]
        return error_response("invalid_request", "The request contains invalid fields.", 422, details)

    @application.exception_handler(HTTPException)
    async def http_error_handler(_request: Request, error: HTTPException):
        return error_response("not_found" if error.status_code == 404 else "http_error",
                              "The requested resource was not found." if error.status_code == 404 else "The request could not be completed.",
                              error.status_code)

    @application.exception_handler(SQLAlchemyError)
    async def database_error_handler(_request: Request, _error: SQLAlchemyError):
        logging.getLogger(__name__).error("Database operation failed; check migration and connection configuration.")
        return error_response("database_unavailable", "The data store is unavailable. Check database readiness and migrations.", 503)

    @application.exception_handler(Exception)
    async def unexpected_error_handler(_request: Request, error: Exception):
        logging.getLogger(__name__).error("Unhandled request failure (%s)", type(error).__name__)
        return error_response("internal_error", "The request could not be completed safely.", 500)

    return application


app = create_app()
