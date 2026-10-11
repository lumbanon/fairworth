from app.providers.base import ProviderError
from app.services.cache_service import CachedResult
from app.services.company_service import combined_status, warning
from app.services.metrics import calculate_metrics
from app.services.normalization import extract_observations, normalize_company_facts


class FinancialService:
    def __init__(self, companies, sec, cache, repository, settings):
        self.companies, self.sec, self.cache = companies, sec, cache
        self.repository, self.settings = repository, settings

    async def dataset(self, ticker):
        company, identity = await self.companies.company_identity(ticker)
        company_id = self.repository.save_company(company)

        async def load():
            raw = await self.cache.get_or_load(f"sec:facts:{company['cik']}", self.settings.sec_cache_ttl_seconds,
                                               "sec-edgar", lambda: self.sec.facts(company["cik"]))
            normalized = normalize_company_facts(raw.payload, cik=company["cik"])
            self.repository.save_financials(company_id, extract_observations(raw.payload), normalized)
            return CachedResult(normalized, raw.status, raw.retrieved_at, raw.warnings)

        result = await self.cache.get_or_load(f"sec:financials:{company['cik']}:{company['ticker']}", self.settings.sec_cache_ttl_seconds,
                                             "sec-edgar", load)
        warnings = list(result.payload.get("warnings", [])) + list(company.get("warnings", [])) + identity.warnings + result.warnings
        status = combined_status(identity.status, result.status, "partial" if warnings else "fresh")
        return company, result, warnings, status

    async def statements(self, ticker, period, limit):
        company, result, warnings, status = await self.dataset(ticker)
        periods = sorted(result.payload.get(period, []), key=lambda item: item["end_date"], reverse=True)[:limit]
        if not periods:
            warnings.append(warning(period, "no_reporting_periods", f"No usable {period} financial statement periods are available."))
            status = combined_status(status, "partial")
        return {"ticker": company["ticker"], "currency": "USD", "period": period, "periods": periods,
                "status": status, "warnings": warnings, "source_references": result.payload.get("source_references", []),
                "retrieved_at": result.retrieved_at}

    async def metrics(self, ticker, period, limit):
        company, result, warnings, status = await self.dataset(ticker)
        # Compute growth before truncating history so the earliest displayed year
        # can still use its correctly aligned preceding fiscal year.
        computed = calculate_metrics(result.payload.get(period, []))
        warnings.extend(computed.get("warnings", []))
        periods = sorted(computed.get("periods", []), key=lambda item: item["end_date"], reverse=True)[:limit]
        return {"ticker": company["ticker"], "periods": periods, "retrieved_at": result.retrieved_at,
                "status": combined_status(status, "partial" if warnings else "fresh"), "warnings": warnings}

    async def data_status(self, ticker):
        company, result, warnings, status = await self.dataset(ticker)
        if company.get("has_multiple_share_classes") and not any(item["code"] == "share_class_basis_unverified" for item in warnings):
            warnings.append(warning("shares", "share_class_basis_unverified",
                                    "Financial share counts may represent multiple listed classes; their basis has not been verified against this quoted class."))
            status = combined_status(status, "partial")
        market = None
        market_status = "unavailable"
        try:
            market = await self.companies.market_quote(company["ticker"], financial_currency="USD")
            market_status = market["status"]
            warnings.extend(market["warnings"])
            status = combined_status(status, market_status)
        except ProviderError as error:
            warnings.append(warning("market_price", error.code, error.message))
            status = combined_status(status, "partial")
        available = {}
        for kind in ("annual", "quarterly"):
            periods = sorted(result.payload.get(kind, []), key=lambda item: item["end_date"], reverse=True)
            available[kind] = [{key: period.get(key) for key in ("fiscal_year", "fiscal_period", "start_date", "end_date")}
                               for period in periods[:20]]
        annual = result.payload.get("annual", [])
        latest = max(annual, key=lambda item: item["end_date"]) if annual else None
        required = ("revenue", "net_income", "operating_cash_flow", "capital_expenditures", "free_cash_flow",
                    "cash_and_cash_equivalents", "total_debt", "shareholders_equity", "weighted_average_diluted_shares")
        missing = [field for field in required if not latest or latest.get("metrics", {}).get(field) is None]
        return {"ticker": company["ticker"], "status": combined_status(status, "partial" if missing else "fresh"),
                "last_financial_update": result.retrieved_at,
                "last_market_update": market.get("price_timestamp") if market else None,
                "available_periods": available, "missing_fields": missing,
                "provider_status": {"financial": {"provider": "sec-edgar", "status": result.status},
                                    "market": {"provider": self.companies.market.name, "status": market_status}},
                "warnings": warnings}
