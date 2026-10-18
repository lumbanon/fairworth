"""Cached dated evidence for assumptions, separate from official financial facts.

Provider restrictions and missing mappings remain explicit. The service never
stores user overrides and never obtains an ORCL quote from profile price fields.
"""
import asyncio
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
import re

from app.core.database import utcnow
from app.providers.base import ProviderError
from app.services.security_identity import cache_scope, market_call, check_provider_identity
from app.services.cache_service import CachedResult
from app.services.normalization import NORMALIZATION_VERSION, extract_observations, normalize_company_facts
from app.valuation.inputs import normalize_annual_period, number, day


EVIDENCE_VERSION = "2.0.0"
# Raw provider contracts are unchanged. Reuse these dated caches while native
# annual reconstructions are isolated by the new interpretation versions.
PROVIDER_CACHE_VERSION = "1.0.0"
OPTIONAL_SOURCE_BUDGET_SECONDS = 3.0
TREASURY_CACHED_OBSERVATION_MAX_AGE_DAYS = 7


def _instant(value):
    return value.isoformat() if isinstance(value, (date, datetime)) else value


def _record(value=None, *, unit=None, provider=None, source_type="unavailable", description="Required evidence is unavailable.",
            observation_date=None, period=None, retrieved_at=None, formula=None, warnings=None, **extra):
    value = number(value)
    return {"value": value, "unit": unit,
            "state": "unavailable" if value is None else "verified_zero" if value == 0 else "verified_value",
            "source_type": source_type if value is not None else "unavailable", "source_category": source_type,
            "provider": provider, "source_provider": provider, "source_description": description,
            "observation_date": _instant(observation_date), "period": period,
            "retrieved_at": _instant(retrieved_at), "derivation_formula": formula,
            "kind": "policy" if source_type == "policy" else "estimate" if source_type in {"derived", "market_estimate"} else "fact" if value is not None else "unavailable",
            "warnings": warnings or [], "editable": True, **extra}


def original_annual_periods(raw, normalized, company, retrieved_at):
    """Reconstruct native annual publications, never future restated EPS.

    Each vintage contains only observations published in its own accession.
    Reported EPS and weighted shares are checked against NI before declaring
    their native US-GAAP publication a comparable dated per-share basis.
    """
    observations = extract_observations(raw)
    as_of = day(str(_instant(retrieved_at) or "")[:10])
    by_accession = {}
    ends = {}
    for obs in observations:
        if obs.get("form") not in {"10-K", "10-K/A"} or not obs.get("accn"):
            continue
        by_accession.setdefault(obs["accn"], []).append(obs)
        start, end = day(obs.get("start")), day(obs.get("end"))
        if start and end and 335 <= (end - start).days + 1 <= 395:
            ends[obs["accn"]] = max(ends.get(obs["accn"], ""), obs["end"])
    selected = []
    periods = sorted(normalized.get("annual", []), key=lambda row: row.get("end_date", ""))[-12:]
    for period in periods:
        end = day(period.get("end_date"))
        if end is None:
            continue
        candidates = []
        for accession, records in by_accession.items():
            if ends.get(accession) != period["end_date"]:
                continue
            native = [obs for obs in records if obs.get("form") == "10-K" and obs.get("fp") == "FY"
                      and obs.get("fy") == period.get("fiscal_year") and obs.get("start") == period.get("start_date")
                      and obs.get("end") == period["end_date"] and day(obs.get("filed"))
                      and (as_of is None or day(obs["filed"]) <= as_of)
                      and 0 <= (day(obs["filed"]) - end).days <= 180]
            if native:
                candidates.append((min(obs["filed"] for obs in native), accession, records))
        if not candidates:
            continue
        publication, accession, records = min(candidates, key=lambda item: (item[0], item[1]))
        facts = {}
        for obs in records:
            if not obs.get("metric") or obs.get("filed") != publication:
                continue
            definition = facts.setdefault(obs["taxonomy"], {}).setdefault(obs["concept"], {"units": {}})
            definition["units"].setdefault(obs["unit"], []).append({key: obs.get(key) for key in
                                                                   ("start", "end", "val", "filed", "accn", "form", "fy", "fp", "frame") if obs.get(key) is not None})
        vintage = normalize_company_facts({"cik": raw.get("cik"), "facts": facts}, cik=company.get("cik"))
        native_period = next((row for row in vintage["annual"] if row["start_date"] == period.get("start_date")
                              and row["end_date"] == period["end_date"]), None)
        if native_period is None:
            continue
        canonical = normalize_annual_period(native_period, normalized.get("currency"), retrieved_at)
        if canonical is None:
            continue
        canonical["publication_date"] = publication
        canonical["source_accession"] = accession
        eps, shares, income = (canonical["metrics"].get(key) for key in
                               ("diluted_eps", "weighted_average_diluted_shares", "net_income"))
        basis = (company.get("has_multiple_share_classes") is False and eps is not None and shares is not None
                 and shares > 0 and income is not None and abs(income / shares - eps) <= .02)
        eps_fact = canonical["facts"].get("diluted_eps")
        if eps_fact:
            eps_fact.update(split_basis_date=publication, split_basis_verified=basis,
                            split_basis_method="Native US-GAAP annual filing EPS and diluted shares, reconciled to same-publication net income within $0.02/share; split events are aligned separately.")
        canonical["eps_split_basis_date"] = publication
        canonical["eps_split_basis_verified"] = basis
        selected.append(canonical)
    return selected


def latest_sec_shares(raw, company, retrieved_at):
    today = datetime.now(UTC).date()
    candidates = []
    for obs in extract_observations(raw):
        if obs.get("taxonomy") != "dei" or obs.get("concept") != "EntityCommonStockSharesOutstanding":
            continue
        value, end, filed = number(obs.get("value")), day(obs.get("end")), day(obs.get("filed"))
        if (obs.get("unit") != "shares" or obs.get("start") is not None or value is None or value <= 0
                or end is None or filed is None or not end <= filed <= today or obs.get("form") not in {"10-K", "10-K/A", "10-Q", "10-Q/A"}
                or not re.fullmatch(r"\d{10}-\d{2}-\d{6}", str(obs.get("accn") or ""))):
            continue
        candidates.append(obs)
    if not candidates:
        return _record(unit="shares", provider="sec-edgar", description="No usable dated SEC common shares outstanding observation.")
    observation_day = max(obs["end"] for obs in candidates)
    on_day = [obs for obs in candidates if obs["end"] == observation_day]
    filed = max(obs["filed"] for obs in on_day)
    on_day = [obs for obs in on_day if obs["filed"] == filed]
    values = {obs["value"] for obs in on_day}
    if len(values) != 1:
        return _record(unit="shares", provider="sec-edgar", description="Conflicting latest SEC current common share observations.")
    verified = company.get("has_multiple_share_classes") is False or company.get("share_class_basis_verified") is True
    warnings = ["Dated filing-cover common shares are not a live current-day observation; future issuance, buybacks and splits may change the count."]
    if not verified:
        warnings.append("Issuer-wide common shares cannot be assigned to the quoted class without verified class compatibility.")
    return _record(values.pop(), unit="shares", provider="sec-edgar", source_type="reported",
                   description="SEC DEI EntityCommonStockSharesOutstanding, most recent valid filing-cover observation.",
                   observation_date=observation_day, retrieved_at=retrieved_at, warnings=warnings,
                   filed=filed, provenance=on_day, share_basis="dated_common_shares_outstanding", scope_verified=verified,
                   source_id=f"sec:dei:{company.get('cik')}:{on_day[0]['accn']}:{observation_day}")


class AutomaticInputsService:
    def __init__(self, companies, financials, settings, treasury=None):
        self.companies, self.financials, self.settings, self.treasury = companies, financials, settings, treasury
        self.cache = companies.cache

    async def _bounded(self, loader):
        """Bound the entire optional operation, including provider retries."""
        deadline = min(OPTIONAL_SOURCE_BUDGET_SECONDS, self.settings.provider_timeout_seconds)
        try:
            return await asyncio.wait_for(loader(), timeout=deadline)
        except TimeoutError:
            raise ProviderError("provider_timeout", "This optional financial source exceeded its retrieval time budget.", 504, True) from None

    async def _optional(self, key, provider, loader, *, ttl=None):
        ttl = ttl or self.settings.valuation_assumption_cache_seconds

        async def safe_load():
            try:
                return {"available": True, "data": await self._bounded(loader)}
            except ProviderError as error:
                existing = self.cache._read(key)
                if existing is not None and isinstance(existing.payload, dict) and existing.payload.get("available"):
                    # Preserve usable historical evidence with the established
                    # stale-on-error behavior instead of replacing it by null.
                    raise
                # Preserve safe error codes; never serialize upstream URLs/body.
                return CachedResult({"available": False, "error_code": error.code, "message": error.message},
                                    "fresh", utcnow(), [], cache_ttl_seconds=300)
        result = await self.cache.get_or_load(key, ttl, provider, safe_load)
        payload = result.payload
        return {**payload, "status": result.status if payload.get("available") else "unavailable",
                "retrieved_at": _instant(result.retrieved_at), "warnings": result.warnings,
                "provider": provider, "source_id": key}

    async def _prices(self, ticker, company=None):
        company = company or {"ticker": ticker}
        scope = cache_scope(company)
        market = self.companies.market
        if not getattr(market, "enabled", False) or not hasattr(market, "splits"):
            return {"prices": [], "provider": market.name, "status": "unavailable", "warnings": ["Compatible historical price/split evidence is unavailable."]}
        # Exactly the existing company-service key and loader, with the largest
        # supported history window. Provider rows retain their adjustment basis.
        try:
            result = await self.cache.get_or_load(f"market:{market.name}:prices:{scope}:2000", self.settings.historical_cache_ttl_seconds,
                                                 market.name, lambda: self._bounded(lambda: market_call(market, "historical_prices", company, 2000)))
            rows = deepcopy(result.payload)
            return {"prices": rows, "provider": market.name, "retrieved_at": _instant(result.retrieved_at),
                    "status": result.status, "warnings": result.warnings,
                    "adjustment_basis": rows[0].get("adjustment_basis") if rows else None,
                    "adjustment_date": rows[0].get("adjustment_date") if rows else None,
                    "currency": rows[0].get("currency") if rows else None,
                    "source_id": f"market:{market.name}:prices:{scope}:2000"}
        except ProviderError as error:
            return {"prices": [], "provider": market.name, "status": "unavailable", "error_code": error.code,
                    "warnings": [error.message]}

    async def _splits(self, ticker, company=None):
        company = company or {"ticker": ticker}
        scope = cache_scope(company)
        market = self.companies.market
        if not hasattr(market, "splits"):
            return {"splits": [], "complete": False, "status": "unavailable", "provider": market.name}
        result = await self._optional(f"market:{market.name}:splits:{scope}:v{PROVIDER_CACHE_VERSION}", market.name, lambda: market_call(market, "splits", company))
        return {**result, "splits": result.get("data", []), "complete": bool(result.get("available")),
                "adjustment_date": str(result.get("retrieved_at", ""))[:10]}

    async def _treasury(self):
        if self.treasury is None or not self.settings.valuation_treasury_enabled:
            return _record(unit="fraction", provider="us-treasury", description="Automatic Treasury yield retrieval is disabled or unavailable.", status="unavailable")
        today = datetime.now(UTC).date()
        result = await self._optional(f"treasury:10year:{today.isoformat()}:v{PROVIDER_CACHE_VERSION}",
                                      self.treasury.name, self.treasury.risk_free_rate)
        if not result.get("available"):
            fallback = self._cached_treasury_observation(today, result)
            if fallback is not None:
                return fallback
            return _record(unit="fraction", provider=self.treasury.name, description=result.get("message", "Treasury yield unavailable."),
                           warnings=[result.get("error_code", "missing_risk_free_rate")], status="unavailable")
        warnings = list(result["data"].get("warnings", []))
        warnings.extend(item.get("message", "") if isinstance(item, dict) else str(item) for item in result["warnings"])
        return {**result["data"], "source_id": result["source_id"], "retrieved_at": result["retrieved_at"],
                "status": result["status"], "warnings": warnings, "editable": True}

    def _cached_treasury_observation(self, today, failure):
        """Reuse recent dated observations across day-key changes, without I/O.

        The Treasury provider's existing freshness convention is seven calendar
        days. Prior snapshots retain their observation and retrieval timestamps;
        neither today's negative cache nor any positive snapshot is rewritten.
        """
        candidates = []
        for offset in range(1, TREASURY_CACHED_OBSERVATION_MAX_AGE_DAYS + 1):
            key = f"treasury:10year:{(today - timedelta(days=offset)).isoformat()}:v{PROVIDER_CACHE_VERSION}"
            entry = self.cache._read(key)
            if entry is None or entry.provider != self.treasury.name or not isinstance(entry.payload, dict) or not entry.payload.get("available"):
                continue
            record = entry.payload.get("data")
            if not isinstance(record, dict):
                continue
            observed, value = day(record.get("observation_date")), number(record.get("value"))
            if (observed is None or not 0 <= (today - observed).days <= TREASURY_CACHED_OBSERVATION_MAX_AGE_DAYS
                    or value is None or not -.05 <= value <= .25 or record.get("unit") != "fraction"
                    or record.get("state") not in {"verified_value", "verified_zero"}
                    or (record.get("state") == "verified_zero") != (value == 0)
                    or observed > entry.retrieved_at.date() or entry.retrieved_at.date() > today):
                continue
            candidates.append((observed, entry.retrieved_at, key, deepcopy(record)))
        if not candidates:
            return None
        _, cached_at, key, record = max(candidates, key=lambda item: (item[0], item[1]))
        warnings = [item.get("message", "") if isinstance(item, dict) else str(item) for item in record.get("warnings", [])]
        warnings.extend(item.get("message", "") if isinstance(item, dict) else str(item) for item in failure.get("warnings", []))
        code = failure.get("error_code", "missing_risk_free_rate")
        warnings.append(f"Using the cached Treasury observation dated {record['observation_date']} because the current-day refresh is unavailable ({code}); original source dates are retained.")
        return {**record, "provider": self.treasury.name, "source_provider": self.treasury.name,
                "source_id": key, "retrieved_at": record.get("retrieved_at") or _instant(cached_at),
                "status": "stale", "warnings": list(dict.fromkeys(warnings)), "editable": True}

    async def _beta(self, ticker, company=None):
        company = company or {"ticker": ticker}
        scope = cache_scope(company)
        market = self.companies.market
        if not getattr(market, "enabled", False):
            return _record(unit="ratio", description="An authorized beta provider is not configured.", status="unavailable")
        try:
            enrichment = await self.cache.get_or_load(f"market:{market.name}:profile:{scope}", self.settings.company_cache_ttl_seconds,
                                                      market.name, lambda: self._bounded(lambda: market_call(market, "profile", company)))
            if market.name == "fmp" and "beta" not in enrichment.payload:
                # Phase 3 persisted profiles predate beta metadata. Backfill
                # once through the same authorized endpoint/key. A present null
                # beta is genuine absence and does not trigger another call.
                refreshed = await self._bounded(lambda: market_call(market, "profile", company))
                refreshed_at = self.cache._write(f"market:{market.name}:profile:{scope}", refreshed,
                                                   self.settings.company_cache_ttl_seconds, market.name)
                enrichment = CachedResult(refreshed, "fresh", refreshed_at, [])
            beta = number(enrichment.payload.get("beta"))
            check_provider_identity(company, enrichment.payload)
            valid = beta is not None and -5 <= beta <= 10
            warnings = ["Provider beta estimation lookback and return frequency are not exposed; retrieval date is not a separately supplied calculation date."]
            warnings.extend(item.get("message", "") if isinstance(item, dict) else str(item) for item in enrichment.warnings)
            return _record(beta if valid else None, unit="ratio", provider=market.name, source_type="market_estimate",
                           description="FMP profile current beta, observed when the profile snapshot was retrieved; provider estimation window/frequency unavailable.",
                           observation_date=enrichment.retrieved_at.date(), retrieved_at=enrichment.retrieved_at,
                           methodology=enrichment.payload.get("beta_methodology"), status=enrichment.status,
                           warnings=warnings, source_id=f"market:{market.name}:profile:{scope}")
        except ProviderError as error:
            return _record(unit="ratio", provider=market.name, description=error.message, warnings=[error.code], status="unavailable")

    async def _supplemental(self, ticker, company=None):
        company = company or {"ticker": ticker}
        scope = cache_scope(company)
        market = self.companies.market
        if not hasattr(market, "financial_statements"):
            return {}
        async def load(kind):
            result = await self._optional(f"market:{market.name}:statement:{scope}:{kind}:annual:v{PROVIDER_CACHE_VERSION}", market.name,
                                          lambda: market_call(market, "financial_statements", company, kind))
            return kind, result
        return dict(await asyncio.gather(load("balance_sheet"), load("cash_flow")))

    def _erp(self):
        s = self.settings
        value = number(s.valuation_erp_value)
        publication = s.valuation_erp_publication_date
        if (value is None or not 0 < value <= .25 or not s.valuation_erp_source.strip()
                or not s.valuation_erp_methodology.strip() or publication is None or day(_instant(publication)) is None
                or day(_instant(publication)) > datetime.now(UTC).date() or s.valuation_erp_market != "US"):
            return _record(unit="fraction", description="No complete configured US equity-risk-premium research policy (value, source, publication date and methodology).")
        return _record(value, unit="fraction", provider=s.valuation_erp_source, source_type="policy",
                       description="Configured US ERP research-policy estimate; not a live market observation.",
                       observation_date=publication, publication_date=_instant(publication), applicable_market=s.valuation_erp_market,
                       methodology=s.valuation_erp_methodology, warnings=["ERP remains a research-policy estimate and materially affects CAPM/WACC."],
                       source_id=f"policy:erp:{_instant(publication)}")

    async def evidence(self, ticker, profile, normalized, retrieved_at):
        if not self.settings.valuation_automatic_inputs_enabled:
            return {}
        company = {"ticker": ticker, **profile.get("company", profile)}
        raw = await self.cache.get_or_load(f"sec:facts:{company['cik']}", self.settings.sec_cache_ttl_seconds,
                                           "sec-edgar", lambda: self.financials.sec.facts(company["cik"]))
        # Native vintage reconstruction is a separate versioned analytics layer.
        native = await self.cache.get_or_load(f"sec:annual-publications:{company['cik']}:{cache_scope(company)}:{raw.retrieved_at.isoformat()}:v{EVIDENCE_VERSION}:n{NORMALIZATION_VERSION}",
                                              self.settings.sec_cache_ttl_seconds, "sec-edgar",
                                              lambda: self._native(raw.payload, normalized, company, raw.retrieved_at))
        # All independent optional sources share one parallel retrieval phase;
        # one slow Treasury/statement cannot serially postpone successful P/E.
        prices, splits, treasury, beta, supplemental = await asyncio.gather(
            self._prices(ticker, company), self._splits(ticker, company), self._treasury(), self._beta(ticker, company), self._supplemental(ticker, company))
        observations = {"current_shares": latest_sec_shares(raw.payload, company, raw.retrieved_at),
                        "risk_free_rate": treasury, "equity_risk_premium": self._erp(), "beta": beta}
        provider_status = {"historical_prices": prices.get("status"), "splits": splits.get("status")}
        latest = max(normalized.get("annual", []), key=lambda row: row.get("end_date", ""), default=None)
        if latest:
            canonical = normalize_annual_period(latest, normalized.get("currency"), retrieved_at)
            if canonical:
                for source, target in {"total_debt": "debt", "cash_and_cash_equivalents": "cash", "minority_interest": "minority_interest",
                                       "depreciation_and_amortization": "depreciation_and_amortization", "interest_expense": "interest_expense",
                                       "depreciation_expense": "depreciation_expense", "intangible_amortization_expense": "intangible_amortization_expense",
                                       "preferred_stock_value_outstanding": "nonredeemable_preferred_equity",
                                       "preferred_stock_stated_value": "preferred_stock_stated_value",
                                       "shares_outstanding": "period_end_shares", "weighted_average_diluted_shares": "diluted_weighted_average_shares",
                                       "weighted_average_basic_shares": "basic_weighted_average_shares"}.items():
                    fact = canonical["facts"].get(source, {})
                    observations[target] = _record(fact.get("value"), unit=fact.get("unit"), provider="sec-edgar", source_type=fact.get("source_type", "unavailable"),
                                                   description=f"SEC {source.replace('_', ' ')} for the selected annual period; original scope retained.",
                                                   observation_date=latest["end_date"], period=fact.get("period"), retrieved_at=retrieved_at,
                                                   provenance=fact.get("provenance", []), warnings=[item.get("message", "") for item in fact.get("warnings", [])])
        # Aggregate preferred claim and other nonoperating assets cannot be
        # established merely because a nonredeemable stock concept is zero.
        for key in ("preferred_equity", "other_nonoperating_assets", "operating_nwc", "net_borrowing"):
            observations[key] = _record(unit=normalized.get("currency"), description=f"Complete {key.replace('_', ' ')} scope is unverified; no missing component is assumed zero.", state="unknown")
        # Supplemental access is capability-based and failure-isolated. Raw
        # statements are retained for reconciliation, never trusted as ratios.
        for kind, result in supplemental.items():
            provider_status[kind] = result.get("error_code") or result["status"]
        warnings = [item for item in raw.warnings + native.warnings]
        return {"methodology_version": EVIDENCE_VERSION, "normalization_version": NORMALIZATION_VERSION,
                "historical_prices": prices, "splits": splits,
                "historical_annual_periods": native.payload, "observations": observations,
                "supplemental_statements": supplemental, "provider_status": provider_status, "warnings": warnings,
                "financial_snapshot_date": _instant(raw.retrieved_at)}

    @staticmethod
    async def _native(raw, normalized, company, retrieved_at):
        return original_annual_periods(raw, normalized, company, retrieved_at)
