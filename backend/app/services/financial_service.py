from app.providers.base import ProviderError, normalize_cik
from app.core.exceptions import ApiError
from app.services.security_identity import applicability, cache_scope, security_identity, scope_kwargs
from app.services.cache_service import CachedResult
from app.services.company_service import combined_status, warning
from app.services.metrics import calculate_metrics
from app.services.normalization import NORMALIZATION_VERSION, extract_observations, normalize_company_facts
from app.core.database import as_utc, utcnow
from app.repositories.financial_repository import parse_instant


class FinancialService:
    def __init__(self, companies, sec, cache, repository, settings):
        self.companies, self.sec, self.cache = companies, sec, cache
        self.repository, self.settings = repository, settings

    @staticmethod
    def _validate_raw_identity(raw, company):
        if not isinstance(raw, dict):
            raise ProviderError("invalid_provider_response", "SEC facts are not a usable issuer document.", 502)
        try:
            actual = normalize_cik(raw["cik"]) if raw.get("cik") is not None else None
            expected = normalize_cik(company["cik"])
        except ProviderError:
            raise ProviderError("incompatible_financial_identity", "SEC facts contain an invalid issuer identifier.", 502) from None
        if (company.get("instrument_id") and actual is None) or actual is not None and actual != expected:
            raise ProviderError("incompatible_financial_identity", "SEC facts do not establish the issuer identifier required for this selected security.", 502)
        return raw

    async def dataset(self, ticker, instrument_id=None, listing_id=None):
        company, identity = await self.companies.company_identity(ticker, **scope_kwargs(instrument_id, listing_id))
        gate = applicability(company)
        if gate and gate[0] in {"unsupported_instrument_type", "inactive_listing", "identity_ambiguous"}:
            raise ApiError(gate[0], gate[1], 422)
        if not company.get("cik"):
            raise ApiError("missing_cik", "Financial statements require a verified SEC issuer mapping.", 422)
        imported = self.repository.imported_dataset(company.get("issuer_id"), company["cik"])
        company_id = imported["company_id"] if imported else self.repository.save_company(company)

        async def load():
            async def raw_load():
                return self._validate_raw_identity(await self.sec.facts(company["cik"]), company)
            raw = await self.cache.get_or_load(f"sec:facts:{company['cik']}", self.settings.sec_cache_ttl_seconds,
                                               "sec-edgar", raw_load)
            self._validate_raw_identity(raw.payload, company)
            normalized = normalize_company_facts(raw.payload, cik=company["cik"])
            if company.get("instrument_id") and not normalized.get("annual") and not normalized.get("quarterly"):
                # The supported mapper is USD/US-GAAP. Empty IFRS-only results
                # do not establish USD reporting or zero-valued statements.
                normalized["currency"] = None
                if "ifrs-full" in raw.payload.get("facts", {}):
                    normalized.setdefault("warnings", []).append(warning("accounting_standard", "unsupported_ifrs_normalization", "IFRS source observations are retained, but compatible normalized financial fields are unavailable; no US GAAP or currency conversion was inferred."))
            self.repository.save_financials(company_id, extract_observations(raw.payload), normalized)
            # Cache-only metadata is added after saving the financial snapshot;
            # source expiry cannot change financial snapshot hashes or values.
            normalized["_source_cache_provenance"] = {
                "retrieved_at": as_utc(raw.retrieved_at).isoformat(),
                "expires_at": as_utc(raw.expires_at).isoformat() if raw.expires_at is not None else None}
            return CachedResult(normalized, raw.status, raw.retrieved_at, raw.warnings, expires_at=raw.expires_at)

        if imported:
            payload = imported["payload"]
            payload["_source_cache_provenance"] = {"retrieved_at": imported["retrieved_at"].isoformat(),
                "expires_at": imported["expires_at"].isoformat() if imported["expires_at"] else None}
            payload["_import_provenance"] = imported["provenance"]
            fresh = imported["expires_at"] is not None and imported["expires_at"] > utcnow()
            notes = [] if fresh else [warning("financial_source", "imported_financial_source_stale",
                "Imported SEC evidence retains its original retrieval and expiry; the import did not renew financial currentness.")]
            result = CachedResult(payload, "fresh" if fresh else "stale", imported["retrieved_at"], notes,
                                  expires_at=imported["expires_at"])
        else:
            result = await self.cache.get_or_load(f"sec:financials:{company['cik']}:{cache_scope(company)}:v{NORMALIZATION_VERSION}", self.settings.sec_cache_ttl_seconds,
                                                 "sec-edgar", load)
        source_clock = result.payload.get("_source_cache_provenance") or {}
        source_retrieved, source_expiry = parse_instant(source_clock.get("retrieved_at")), parse_instant(source_clock.get("expires_at"))
        result.expires_at = (min(as_utc(result.expires_at), as_utc(source_expiry))
                             if result.expires_at is not None and source_expiry is not None
                             and source_retrieved is not None and as_utc(source_retrieved) == as_utc(result.retrieved_at) else None)
        # The normalized document has no raw SEC `cik` field. Its identity is
        # established by the validated raw source and issuer-scoped cache key.
        if result.payload.get("cik") is not None and normalize_cik(result.payload["cik"]) != normalize_cik(company["cik"]):
            raise ApiError("incompatible_financial_identity", "Normalized facts do not match the resolved issuer.", 502)
        warnings = list(result.payload.get("warnings", [])) + list(company.get("warnings", [])) + identity.warnings + result.warnings
        status = combined_status(identity.status, result.status, "partial" if warnings else "fresh")
        return company, result, warnings, status

    async def statements(self, ticker, period, limit, instrument_id=None, listing_id=None):
        company, result, warnings, status = await self.dataset(ticker, **scope_kwargs(instrument_id, listing_id))
        periods = sorted(result.payload.get(period, []), key=lambda item: item["end_date"], reverse=True)[:limit]
        if not periods:
            warnings.append(warning(period, "no_reporting_periods", f"No usable {period} financial statement periods are available."))
            status = combined_status(status, "partial")
        return {"ticker": company["ticker"], "identity": security_identity(company), "currency": result.payload.get("currency"), "period": period, "periods": periods,
                "status": status, "warnings": warnings, "source_references": result.payload.get("source_references", []),
                "retrieved_at": result.retrieved_at, "financial_import": result.payload.get("_import_provenance")}

    async def metrics(self, ticker, period, limit, instrument_id=None, listing_id=None):
        company, result, warnings, status = await self.dataset(ticker, **scope_kwargs(instrument_id, listing_id))
        # Compute growth before truncating history so the earliest displayed year
        # can still use its correctly aligned preceding fiscal year.
        computed = calculate_metrics(result.payload.get(period, []))
        warnings.extend(computed.get("warnings", []))
        periods = sorted(computed.get("periods", []), key=lambda item: item["end_date"], reverse=True)[:limit]
        return {"ticker": company["ticker"], "identity": security_identity(company), "periods": periods, "retrieved_at": result.retrieved_at,
                "status": combined_status(status, "partial" if warnings else "fresh"), "warnings": warnings,
                "financial_import": result.payload.get("_import_provenance")}

    async def data_status(self, ticker, instrument_id=None, listing_id=None):
        company, result, warnings, status = await self.dataset(ticker, **scope_kwargs(instrument_id, listing_id))
        if company.get("has_multiple_share_classes") and not any(item["code"] == "share_class_basis_unverified" for item in warnings):
            warnings.append(warning("shares", "share_class_basis_unverified",
                                    "Financial share counts may represent multiple listed classes; their basis has not been verified against this quoted class."))
            status = combined_status(status, "partial")
        market = None
        market_status = "unavailable"
        try:
            market = await self.companies.market_quote(company["ticker"], financial_currency=result.payload.get("currency"), **({"identity": company} if company.get("instrument_id") else {}))
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
        return {"ticker": company["ticker"], "identity": security_identity(company), "status": combined_status(status, "partial" if missing else "fresh"),
                "last_financial_update": result.retrieved_at,
                "last_market_update": market.get("price_timestamp") if market else None,
                "available_periods": available, "missing_fields": missing,
                "provider_status": {"financial": {"provider": "sec-edgar", "status": result.status},
                                    "market": {"provider": self.companies.market.name, "status": market_status}},
                "warnings": warnings}
