"""Retrieve once, calculate from immutable inputs, never persist user estimates."""
import asyncio
from copy import deepcopy
from contextlib import asynccontextmanager
import time

from starlette.concurrency import run_in_threadpool

from app.core.exceptions import ApiError
from app.core.database import utcnow
from app.providers.base import ProviderError
from app.services.cache_service import CachedResult
from app.services.security_identity import cache_scope, same_identity, applicability, scope_kwargs
from app.valuation.coverage import calculate_with_coverage
from app.valuation.inputs import build_valuation_inputs
from app.valuation.financial_currentness import source_cache_policy, unverified_currentness
from app.valuation.schemas import ValuationRequest


class ValuationService:
    def __init__(self, companies, financials, settings, automatic_inputs=None):
        self.companies, self.financials, self.settings = companies, financials, settings
        self.automatic_inputs = automatic_inputs
        self._snapshots = {}
        self._locks = {}
        self._lock_users = {}
        self.policy = {"forecast_years": settings.valuation_forecast_years,
                       "terminal_growth": settings.valuation_terminal_growth,
                       "cost_of_equity": settings.valuation_benchmark_cost_of_equity,
                       "minimum_forecast_growth": settings.valuation_minimum_forecast_growth,
                       "maximum_forecast_growth": settings.valuation_maximum_forecast_growth,
                       "maximum_annual_growth_dispersion": settings.valuation_maximum_growth_dispersion,
                       "historical_multiple_years": settings.valuation_historical_multiple_years,
                       "historical_multiple_minimum_years": settings.valuation_historical_multiple_minimum_years,
                       "allow_benchmark_cost_of_equity": settings.valuation_allow_benchmark_cost_of_equity}

    @asynccontextmanager
    async def _key_lock(self, scope):
        lock = self._locks.setdefault(scope, asyncio.Lock())
        self._lock_users[scope] = self._lock_users.get(scope, 0) + 1
        try:
            async with lock:
                yield
        finally:
            self._lock_users[scope] -= 1
            if not self._lock_users[scope]:
                self._lock_users.pop(scope)
                self._locks.pop(scope)

    async def inputs(self, ticker, instrument_id=None, listing_id=None):
        # Resolve before process-cache access: a reused symbol cannot inherit a
        # prior issuer's otherwise fresh snapshot.
        if getattr(self.companies, "registry", None) is not None or instrument_id is not None or listing_id is not None:
            identity, _ = await self.companies.company_identity(ticker, **scope_kwargs(instrument_id, listing_id))
            scope = cache_scope(identity)
            kwargs = scope_kwargs(identity.get("instrument_id"), identity.get("listing_id"))
        else:
            scope, kwargs = ticker, {}
        async with self._key_lock(scope):
            cached = self._snapshots.get(scope)
            if cached and time.monotonic() - cached[0] < self.settings.valuation_input_cache_seconds:
                return deepcopy(cached[1])
            profile, dataset = await asyncio.gather(self.companies.profile(ticker, **kwargs), self.financials.dataset(ticker, **kwargs), return_exceptions=True)
            if isinstance(profile, BaseException):
                raise profile
            if isinstance(dataset, BaseException):
                if not isinstance(dataset, (ApiError, ProviderError, TimeoutError)) or getattr(dataset, "code", "") in {"incompatible_financial_identity", "incompatible_security_identity"}:
                    raise dataset
                company = profile["company"]
                warnings = [{"field": "financial_statements", "code": getattr(dataset, "code", "provider_timeout"),
                             "message": str(dataset)}]
                result = CachedResult({"currency": None, "annual": [], "quarterly": []}, "partial", utcnow(), warnings)
                status = "partial"
                financial_source = {"status": "unavailable", "error_code": getattr(dataset, "code", "provider_timeout"), "warnings": deepcopy(warnings)}
            else:
                company, result, warnings, status = dataset
                financial_source = {"status": result.status, "warnings": deepcopy(result.payload.get("warnings", [])) + deepcopy(result.warnings)}
            financial_source["source_cache"] = source_cache_policy(result.retrieved_at, getattr(self.settings, "sec_cache_ttl_seconds", None),
                                                                   actual_expires_at=getattr(result, "expires_at", None))
            # A document download/cache hit is not evidence that the selected
            # annual period is the latest filing applicable to this issuer.
            financial_source["currentness"] = unverified_currentness()
            if not same_identity(profile["company"], company):
                raise ApiError("incompatible_financial_identity", "The financial snapshot does not match the requested company.", 502)
            normalized = {**result.payload, "warnings": warnings}
            inputs = build_valuation_inputs(profile, normalized, result.retrieved_at)
            if self.automatic_inputs is not None and company.get("cik") and result.payload.get("annual") and not applicability(company):
                from app.valuation.automatic import prepare_automatic_inputs
                evidence = await self.automatic_inputs.evidence(ticker, profile, normalized, result.retrieved_at)
                inputs = await run_in_threadpool(prepare_automatic_inputs, inputs, evidence, self.policy)
            inputs["data_status"] = status
            inputs["financial_source_status"] = financial_source
            self._snapshots[scope] = (time.monotonic(), deepcopy(inputs))
            # Bound process-local snapshot retention; persistent financial caching
            # remains owned by Phase 3. No transient adjustment is written to SQL.
            if len(self._snapshots) > 100:
                oldest = min(self._snapshots, key=lambda key: self._snapshots[key][0])
                self._snapshots.pop(oldest, None)
            return inputs

    async def calculate(self, ticker, request=None, instrument_id=None, listing_id=None):
        request = request or ValuationRequest()
        if request.context == "dated_intrinsic":
            from app.services.dated_valuation_inputs import build_dated_inputs
            from app.valuation.dated_intrinsic import request_scope
            request_scope(request)
            registry = getattr(self.companies, "registry", None)
            if registry is None:
                raise ApiError("dated_security_registry_required", "The explicit historical workflow requires retained registry and imported financial evidence.", 422)
            inputs = await run_in_threadpool(build_dated_inputs, registry, self.financials.repository, self.settings,
                                             ticker, instrument_id, listing_id)
        else:
            inputs = await self.inputs(ticker, **scope_kwargs(instrument_id, listing_id))
        try:
            return await asyncio.wait_for(run_in_threadpool(calculate_with_coverage, inputs, request, self.policy), timeout=self.settings.valuation_calculation_timeout_seconds)
        except TimeoutError:
            raise ApiError("valuation_timeout", "The bounded valuation calculation exceeded its time limit.", 503) from None
