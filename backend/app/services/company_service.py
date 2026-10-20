import math
from datetime import timedelta

from fastapi.encoders import jsonable_encoder

from app.core.database import as_utc, utcnow
from app.providers.base import ProviderError
from app.core.exceptions import ApiError
from app.services.cache_service import CachedResult
from app.services.security_identity import cache_scope, check_provider_identity, market_call, security_identity, scope_kwargs
from app.repositories.financial_repository import parse_instant


def combined_status(*statuses):
    return "stale" if "stale" in statuses else "partial" if "partial" in statuses else "fresh"


def warning(field, code, message):
    return {"field": field, "code": code, "message": message}


class CompanyService:
    def __init__(self, sec, market, cache, repository, settings, registry=None):
        self.sec, self.market = sec, market
        self.cache, self.repository, self.settings = cache, repository, settings
        self.registry = registry

    async def search(self, query, limit, offset=0, listing_status=None):
        if self.registry is not None:
            filters = {"listing_status": listing_status} if listing_status is not None else {}
            result = await self.registry.search(query, limit, offset, **filters)
            result["registry_as_of"] = result.get("as_of")
            result["next_offset"] = result.get("offset", offset) + result.get("limit", limit) if result.get("has_more") else None
            return result
        if listing_status is not None:
            return {"results": [], "status": "partial", "warnings": [warning("security_registry", "listing_filter_unavailable",
                    "A listing-status filter requires an imported security registry; issuer references do not prove listing status.")],
                    "limit": limit, "offset": offset, "has_more": False, "next_offset": None}
        normalized_query = query.strip().upper()
        result = await self.cache.get_or_load(f"sec:search:{normalized_query}:{limit}",
                                             self.settings.company_cache_ttl_seconds, "sec-edgar",
                                             lambda: self.sec.search(normalized_query, limit))
        return {"results": result.payload, "status": result.status, "warnings": result.warnings}

    async def company_identity(self, ticker, instrument_id=None, listing_id=None):
        if self.registry is None:
            if instrument_id is not None or listing_id is not None:
                raise ApiError("security_registry_unavailable", "An explicit instrument requires the security registry.", 503)
            result = await self.cache.get_or_load(f"sec:company:{ticker}", self.settings.company_cache_ttl_seconds,
                                                 "sec-edgar", lambda: self.sec.company(ticker))
            payload = dict(result.payload)
        else:
            identity = await self.registry.resolve(ticker, **scope_kwargs(instrument_id, listing_id))
            payload = dict(identity)
            registry_status = identity.get("registry_status", "partial")
            registry_warnings = list(identity.get("registry_warnings") or [])
            registry_retrieved = as_utc(parse_instant(identity.get("registry_retrieved_at")))
            result = CachedResult(payload, registry_status, registry_retrieved, registry_warnings)
            if identity.get("cik") and hasattr(self.sec, "company_for_identity"):
                try:
                    result = await self.cache.get_or_load(f"sec:company:{cache_scope(identity)}", self.settings.company_cache_ttl_seconds,
                                                         "sec-edgar", lambda: self.sec.company_for_identity(identity))
                    check_provider_identity(identity, result.payload)
                    payload = {**result.payload, **identity}
                    if not payload.get("filing_regime") and result.payload.get("filing_regime"):
                        payload["filing_regime"] = result.payload["filing_regime"]
                    result = CachedResult(result.payload, combined_status(registry_status, result.status), result.retrieved_at,
                                          registry_warnings + result.warnings)
                except ProviderError as error:
                    if error.code in {"incompatible_financial_identity", "incompatible_security_identity"}:
                        raise
                    result = CachedResult(payload, combined_status(registry_status, "partial"), registry_retrieved,
                                          registry_warnings + [warning("company_profile", error.code, error.message)])
            elif not identity.get("cik"):
                result.warnings.append(warning("cik", "missing_cik", "No verified SEC issuer mapping is available for this security."))
                result.status = "partial"
        sic = str(payload.get("sic") or "")
        sic = sic if len(sic) == 4 and sic.isdigit() else None
        payload["is_bank"] = True if payload.get("instrument_type") == "financial_institution" else sic in {"6021", "6022", "6029", "6035", "6036", "6061", "6062", "6081", "6082", "6099"} if sic else None
        payload["is_reit"] = True if payload.get("instrument_type") == "reit" else sic == "6798" if sic else None
        business = payload.get("issuer_business_category")
        if business in {None, "unknown"} and sic:
            business = "bank" if payload["is_bank"] else "reit" if payload["is_reit"] else "insurance" if 6300 <= int(sic) <= 6399 else "other" if 6000 <= int(sic) <= 6999 else "operating_company"
            payload["issuer_business_category"] = business
            payload["issuer_classification_evidence"] = {"provider": "sec-edgar", "concept": "sic", "value": sic,
                "cik": payload.get("cik"), "url": f"https://data.sec.gov/submissions/CIK{payload['cik']}.json"}
        payload["is_bank"] = True if business == "bank" else payload["is_bank"]
        payload["is_reit"] = True if business == "reit" else payload["is_reit"]
        return payload, result

    async def market_quote(self, ticker, financial_currency=None, identity=None):
        identity = identity or {"ticker": ticker}
        result = await self.cache.get_or_load(f"market:{self.market.name}:quote:{cache_scope(identity)}",
                                             self.settings.market_cache_ttl_seconds, self.market.name,
                                             lambda: market_call(self.market, "quote", identity))
        payload = dict(result.payload)
        check_provider_identity(identity, payload)
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

    async def profile(self, ticker, instrument_id=None, listing_id=None):
        company, identity = await self.company_identity(ticker, **scope_kwargs(instrument_id, listing_id))
        ticker = company["ticker"]
        warnings = list(company.get("warnings", [])) + identity.warnings
        status = combined_status(identity.status, "partial" if warnings else "fresh")
        if company.get("has_multiple_share_classes") and not any(item["code"] == "share_class_basis_unverified" for item in warnings):
            warnings.append(warning("shares", "share_class_basis_unverified",
                                    "Financial share counts may represent multiple listed classes; their basis has not been verified against this quoted class."))
            status = combined_status(status, "partial")
        try:
            enrichment = await self.cache.get_or_load(f"market:{self.market.name}:profile:{cache_scope(company)}",
                                                      self.settings.company_cache_ttl_seconds, self.market.name,
                                                      lambda: market_call(self.market, "profile", company))
            check_provider_identity(company, enrichment.payload)
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
            financial_currency = (company.get("reporting_currency") or (company.get("adr_metadata") or {}).get("reporting_currency")) if company.get("instrument_id") else "USD"
            market = await self.market_quote(ticker, financial_currency=financial_currency, **({"identity": company} if company.get("instrument_id") else {}))
            warnings.extend(market["warnings"])
            status = combined_status(status, market["status"])
        except ProviderError as error:
            warnings.append(warning("market_price", error.code, error.message))
            status = combined_status(status, "partial")
        if company.get("cik"):
            try:
                company_id = self.repository.save_company(company)
                if market:
                    self.repository.save_market(company_id, {**market, "security_identity": security_identity(company)})
            except ApiError as error:
                if error.code != "incompatible_financial_identity":
                    raise
                warnings.append(warning("identity", error.code, error.message))
                status = combined_status(status, "partial")
        references = list(company.get("source_refs", []))
        if company.get("cik") and (not company.get("instrument_id") or identity.payload.get("provider") in {"sec", "sec-edgar"}):
            references.append({"provider": "sec-edgar", "cik": company["cik"],
                               "url": f"https://data.sec.gov/submissions/CIK{company['cik']}.json",
                               "retrieved_at": identity.retrieved_at.isoformat()})
        return {"company": company, "market": market, "status": status, "warnings": warnings,
                "source_references": references}

    async def historical_prices(self, ticker, limit, instrument_id=None, listing_id=None):
        company, identity = await self.company_identity(ticker, **scope_kwargs(instrument_id, listing_id))
        ticker = company["ticker"]
        result = await self.cache.get_or_load(f"market:{self.market.name}:prices:{cache_scope(company)}:{limit}",
                                             self.settings.historical_cache_ttl_seconds, self.market.name,
                                             lambda: market_call(self.market, "historical_prices", company, limit))
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
            quote = await self.market_quote(ticker, **({"identity": company} if company.get("instrument_id") else {}))
            currency = quote.get("currency") or currency
        except ProviderError as error:
            warnings.append(warning("currency", error.code, "Historical price currency could not be confirmed from the market provider."))
        return {"ticker": company["ticker"], "identity": security_identity(company), "currency": currency, "prices": prices, "provider": self.market.name,
                "retrieved_at": result.retrieved_at, "status": combined_status(identity.status, result.status, "partial" if warnings else "fresh"),
                "warnings": warnings, "source_references": [{"provider": self.market.name}]}
