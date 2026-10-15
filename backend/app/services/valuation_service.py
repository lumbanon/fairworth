"""Retrieve once, calculate from immutable inputs, never persist user estimates."""
import asyncio
from copy import deepcopy
import time

from starlette.concurrency import run_in_threadpool

from app.core.exceptions import ApiError
from app.valuation.engine import calculate_valuation
from app.valuation.inputs import build_valuation_inputs
from app.valuation.schemas import ValuationRequest


class ValuationService:
    def __init__(self, companies, financials, settings, automatic_inputs=None):
        self.companies, self.financials, self.settings = companies, financials, settings
        self.automatic_inputs = automatic_inputs
        self._snapshots = {}
        self._locks = {}
        self.policy = {"forecast_years": settings.valuation_forecast_years,
                       "terminal_growth": settings.valuation_terminal_growth,
                       "cost_of_equity": settings.valuation_benchmark_cost_of_equity,
                       "minimum_forecast_growth": settings.valuation_minimum_forecast_growth,
                       "maximum_forecast_growth": settings.valuation_maximum_forecast_growth,
                       "maximum_annual_growth_dispersion": settings.valuation_maximum_growth_dispersion,
                       "historical_multiple_years": settings.valuation_historical_multiple_years,
                       "historical_multiple_minimum_years": settings.valuation_historical_multiple_minimum_years,
                       "allow_benchmark_cost_of_equity": settings.valuation_allow_benchmark_cost_of_equity}

    async def inputs(self, ticker):
        async with self._locks.setdefault(ticker, asyncio.Lock()):
            cached = self._snapshots.get(ticker)
            if cached and time.monotonic() - cached[0] < self.settings.valuation_input_cache_seconds:
                return deepcopy(cached[1])
            profile, dataset = await asyncio.gather(self.companies.profile(ticker), self.financials.dataset(ticker))
            company, result, warnings, status = dataset
            if profile["company"]["cik"] != company["cik"]:
                raise ApiError("incompatible_financial_identity", "The financial snapshot does not match the requested company.", 502)
            normalized = {**result.payload, "warnings": warnings}
            inputs = build_valuation_inputs(profile, normalized, result.retrieved_at)
            if self.automatic_inputs is not None:
                from app.valuation.automatic import prepare_automatic_inputs
                evidence = await self.automatic_inputs.evidence(ticker, profile, normalized, result.retrieved_at)
                inputs = await run_in_threadpool(prepare_automatic_inputs, inputs, evidence, self.policy)
            inputs["data_status"] = status
            self._snapshots[ticker] = (time.monotonic(), deepcopy(inputs))
            # Bound process-local snapshot retention; persistent financial caching
            # remains owned by Phase 3. No transient adjustment is written to SQL.
            if len(self._snapshots) > 100:
                oldest = min(self._snapshots, key=lambda key: self._snapshots[key][0])
                self._snapshots.pop(oldest, None)
                if oldest != ticker and not self._locks[oldest].locked():
                    self._locks.pop(oldest, None)
            return inputs

    async def calculate(self, ticker, request=None):
        inputs = await self.inputs(ticker)
        try:
            return await asyncio.wait_for(run_in_threadpool(calculate_valuation, inputs, request or ValuationRequest(), self.policy), timeout=self.settings.valuation_calculation_timeout_seconds)
        except TimeoutError:
            raise ApiError("valuation_timeout", "The bounded valuation calculation exceeded its time limit.", 503) from None
