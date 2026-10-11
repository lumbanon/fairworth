import math
from datetime import timedelta

from fastapi.encoders import jsonable_encoder

from app.core.database import as_utc, utcnow
from app.providers.base import ProviderError
from app.repositories.financial_repository import parse_instant


def combined_status(*statuses):
    return "stale" if "stale" in statuses else "partial" if "partial" in statuses else "fresh"


def warning(field, code, message):
    return {"field": field, "code": code, "message": message}


class CompanyService:
    def __init__(self, sec, market, cache, repository, settings):
        self.sec, self.market = sec, market
        self.cache, self.repository, self.settings = cache, repository, settings

    async def search(self, query, limit):
        normalized_query = query.strip().upper()
        result = await self.cache.get_or_load(f"sec:search:{normalized_query}:{limit}",
                                             self.settings.company_cache_ttl_seconds, "sec-edgar",
                                             lambda: self.sec.search(normalized_query, limit))
        return {"results": result.payload, "status": result.status, "warnings": result.warnings}

    async def company_identity(self, ticker):
        result = await self.cache.get_or_load(f"sec:company:{ticker}", self.settings.company_cache_ttl_seconds,
                                             "sec-edgar", lambda: self.sec.company(ticker))
        payload = dict(result.payload)
        sic = str(payload.get("sic") or "")
        sic = sic if len(sic) == 4 and sic.isdigit() else None
        payload["is_bank"] = sic in {"6021", "6022", "6029", "6035", "6036", "6061", "6062", "6081", "6082", "6099"} if sic else None
        payload["is_reit"] = sic == "6798" if sic else None
        return payload, result

    async def market_quote(self, ticker, financial_currency=None):
        result = await self.cache.get_or_load(f"market:{self.market.name}:quote:{ticker}",
                                             self.settings.market_cache_ttl_seconds, self.market.name,
                                             lambda: self.market.quote(ticker))
        payload = dict(result.payload)
        warnings = list(payload.get("warnings", [])) + result.warnings
        for field in ("price", "market_cap", "shares_outstanding"):
            value = payload.get(field)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0):
                payload[field] = None
                warnings.append(warning(field, "invalid_market_value", f"The market provider returned an invalid {field.replace('_', ' ')}."))
        timestamp = as_utc(parse_instant(payload.get("price_timestamp")))
        status = result.status
        if timestamp is None:
            warnings.append(warning("price_timestamp", "missing_price_timestamp", "The market price has no usable observation timestamp."))
        elif timestamp < utcnow() - timedelta(seconds=self.settings.market_max_age_seconds):
            status = "stale"
            warnings.append(warning("price_timestamp", "stale_market_price", "The latest available market price is older than the configured maximum age."))
        elif timestamp > utcnow() + timedelta(minutes=5):
            warnings.append(warning("price_timestamp", "future_price_timestamp", "The market price observation timestamp is in the future."))
        if payload.get("price") is None:
            warnings.append(warning("price", "missing_market_price", "A valid market price is unavailable."))
        if payload.get("shares_outstanding") is None:
            warnings.append(warning("shares_outstanding", "missing_share_count", "The market provider did not supply a usable current share count."))
        if not payload.get("currency"):
            warnings.append(warning("currency", "missing_market_currency", "The market provider did not identify the price currency."))
        elif financial_currency and payload["currency"] != financial_currency:
            warnings.append(warning("currency", "incompatible_currencies", "The market price and financial statements use different currencies; no currency conversion is applied."))
        price, shares, cap = (payload.get(key) for key in ("price", "shares_outstanding", "market_cap"))
        if price and shares and cap and abs(cap - price * shares) / cap > 0.1:
            warnings.append(warning("market_cap", "market_cap_basis_mismatch", "Reported market capitalization differs from price multiplied by the supplied share count; the provider figure is preserved."))
        payload.update(price_timestamp=timestamp, provider=self.market.name, retrieved_at=result.retrieved_at,
                       status=combined_status(status, "partial" if warnings else "fresh"), warnings=warnings)
        return jsonable_encoder(payload)

    async def profile(self, ticker):
        company, identity = await self.company_identity(ticker)
        ticker = company["ticker"]
        warnings = list(company.get("warnings", [])) + identity.warnings
        status = combined_status(identity.status, "partial" if warnings else "fresh")
        if company.get("has_multiple_share_classes") and not any(item["code"] == "share_class_basis_unverified" for item in warnings):
            warnings.append(warning("shares", "share_class_basis_unverified",
                                    "Financial share counts may represent multiple listed classes; their basis has not been verified against this quoted class."))
            status = combined_status(status, "partial")
        try:
            enrichment = await self.cache.get_or_load(f"market:{self.market.name}:profile:{ticker}",
                                                      self.settings.company_cache_ttl_seconds, self.market.name,
                                                      lambda: self.market.profile(ticker))
            for field in ("exchange", "sector", "industry", "description", "currency"):
                if enrichment.payload.get(field):
                    company[field] = enrichment.payload[field]
            warnings.extend(enrichment.warnings)
            status = combined_status(status, enrichment.status)
        except ProviderError as error:
            warnings.append(warning("company_profile", error.code, error.message))
            status = combined_status(status, "partial")
        market = None
        try:
            market = await self.market_quote(ticker, financial_currency="USD")
            warnings.extend(market["warnings"])
            status = combined_status(status, market["status"])
        except ProviderError as error:
            warnings.append(warning("market_price", error.code, error.message))
            status = combined_status(status, "partial")
        company_id = self.repository.save_company(company)
        if market:
            self.repository.save_market(company_id, market)
        return {"company": company, "market": market, "status": status, "warnings": warnings,
                "source_references": [{"provider": "sec-edgar", "cik": company["cik"],
                                       "url": f"https://data.sec.gov/submissions/CIK{company['cik']}.json",
                                       "retrieved_at": identity.retrieved_at.isoformat()}]}

    async def historical_prices(self, ticker, limit):
        company, identity = await self.company_identity(ticker)
        ticker = company["ticker"]
        result = await self.cache.get_or_load(f"market:{self.market.name}:prices:{ticker}:{limit}",
                                             self.settings.historical_cache_ttl_seconds, self.market.name,
                                             lambda: self.market.historical_prices(ticker, limit))
        warnings = list(result.warnings) + identity.warnings
        prices = []
        for item in result.payload[:limit]:
            value = item.get("close")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                warnings.append(warning("close", "invalid_market_value", "An invalid historical close observation was omitted."))
                continue
            prices.append(item)
        currency = company.get("currency")
        try:
            quote = await self.market_quote(ticker)
            currency = quote.get("currency") or currency
        except ProviderError as error:
            warnings.append(warning("currency", error.code, "Historical price currency could not be confirmed from the market provider."))
        return {"ticker": company["ticker"], "currency": currency, "prices": prices, "provider": self.market.name,
                "retrieved_at": result.retrieved_at, "status": combined_status(identity.status, result.status, "partial" if warnings else "fresh"),
                "warnings": warnings, "source_references": [{"provider": self.market.name}]}
