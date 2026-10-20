"""Persistent discovery with an optional once-per-process cold bootstrap."""
import asyncio
from datetime import datetime, time as midnight
import time

from starlette.concurrency import run_in_threadpool

from app.providers.base import ProviderError
from app.core.database import utcnow
from app.registry.repository import SecurityRegistryRepository
from app.registry.listing_sources import exchange_mic


class SecurityRegistryService:
    def __init__(self, session_factory, settings, sec=None, cache=None):
        self.repository = SecurityRegistryRepository(session_factory)
        self.settings, self.sec, self.cache = settings, sec, cache
        self._bootstrap_lock = asyncio.Lock()
        self._bootstrap_attempted = False
        self._bootstrap_failure_at = None

    async def ensure_directory(self):
        if self._bootstrap_attempted or await run_in_threadpool(self.repository.has_records):
            return
        if self._bootstrap_failure_at and time.monotonic() - self._bootstrap_failure_at < 60:
            return
        async with self._bootstrap_lock:
            if self._bootstrap_attempted or await run_in_threadpool(self.repository.has_records):
                return
            if not self.sec or not hasattr(self.sec, "security_directory"):
                self._bootstrap_attempted = True
                return
            if not getattr(self.settings, "registry_bootstrap_enabled", False):
                return
            # Source acquisition must itself obey deployment authorization. No
            # fallback calls to search/company or one request per keystroke.
            try:
                if self.cache:
                    result = await self.cache.get_or_load("security-registry:sec-reference:v1",
                                                          getattr(self.settings, "registry_cache_ttl_seconds", 86400),
                                                          "sec-edgar", self.sec.security_directory)
                    bundle = result.payload
                else:
                    bundle = await self.sec.security_directory()
            except Exception:
                self._bootstrap_failure_at = time.monotonic()
                raise
            if isinstance(bundle, dict) and bundle.get("records"):
                await run_in_threadpool(self.import_snapshot, bundle["records"], bundle["provenance"])
                self._bootstrap_attempted = True
            else:
                self._bootstrap_failure_at = time.monotonic()
                raise ProviderError("invalid_provider_response", "The security reference directory contains no usable records.", 502)

    def import_snapshot(self, records, provenance):
        return self.repository.import_snapshot(records, provenance)

    def _reference_status(self, record):
        """Date source observations independently of import/retrieval clocks."""
        source_date = record.get("registry_as_of", record.get("as_of"))
        try:
            observed = datetime.fromisoformat(str(source_date)).date()
        except (TypeError, ValueError):
            return "partial", [{"field": "security_registry", "code": "missing_registry_reference_date",
                                "message": "The security reference has no usable source observation date; current listing identity freshness is unverified."}]
        now = utcnow()
        observed_at = datetime.combine(observed, midnight.min, tzinfo=now.tzinfo)
        if observed > now.date():
            return "partial", [{"field": "security_registry", "code": "future_registry_reference_date",
                                "message": "The security reference source date is in the future; current listing identity freshness is unverified."}]
        if (now - observed_at).total_seconds() > getattr(self.settings, "registry_cache_ttl_seconds", 86400):
            return "stale", [{"field": "security_registry", "code": "stale_registry_reference",
                              "message": f"The security reference source date ({observed.isoformat()}) exceeds the configured freshness period; its original classifications and listing status are retained as dated observations."}]
        return "fresh", []

    def _with_freshness(self, identity):
        status, warnings = self._reference_status(identity)
        verification = dict(identity.get("listing_verification") or {})
        if verification:
            verification.update(freshness=status, stale=status != "fresh")
        resolved_identity_status = identity.get("identity_status")
        linkage = verification.get("issuer_linkage") or identity.get("issuer_linkage")
        if isinstance(linkage, dict) and linkage:
            linkage = dict(linkage)
            link_status, _ = self._reference_status({"registry_as_of": linkage.get("observed_on")})
            symbols = {identity.get("ticker"), *(identity.get("symbol_aliases") or [])}
            matches = (linkage.get("issuer_id") == identity.get("issuer_id")
                       and linkage.get("cik") == identity.get("cik") and bool(identity.get("cik"))
                       and linkage.get("ticker") in symbols
                       and linkage.get("exchange_mic") == exchange_mic(identity.get("exchange"), identity.get("exchange_mic")))
            if not matches:
                link_status = "partial"
            linkage.update(freshness=link_status, stale=link_status != "fresh")
            verification["issuer_linkage"] = linkage
        elif verification.get("status") == "verified":
            link_status, linkage = "partial", {}
        else:
            link_status, linkage = "not_assessed", {}
        if verification.get("status") == "verified" and link_status != "fresh":
            if resolved_identity_status == "verified":
                resolved_identity_status = "reference_only"
            warnings.append({"field": "issuer_linkage", "code": "stale_issuer_symbol_reference" if link_status == "stale" else "issuer_symbol_reference_unverified",
                "message": "The SEC issuer-symbol reference is dated or unverified independently of the listing observation. A fresh directory file does not refresh issuer ownership; financial identity remains reference-only."})
        return {**identity, "registry_status": status, "registry_warnings": warnings,
                "identity_status": resolved_identity_status, "issuer_linkage": linkage,
                **({"listing_verification": verification} if verification else {})}

    async def search(self, query, limit=10, offset=0, listing_status=None):
        await self.ensure_directory()
        filters = {"listing_status": listing_status} if listing_status is not None else {}
        result = await run_in_threadpool(self.repository.search, query, limit, offset, **filters)
        result["results"] = [self._with_freshness(identity) for identity in result["results"]]
        if result.get("registry_empty"):
            return result
        status, warnings = self._reference_status(result)
        for identity in result["results"]:
            if identity["registry_status"] == "stale":
                status = "stale"
            elif identity["registry_status"] == "partial" and status == "fresh":
                status = "partial"
            for warning in identity["registry_warnings"]:
                if warning not in warnings:
                    warnings.append(warning)
        result["status"], result["registry_status"] = status, status
        result["warnings"], result["registry_warnings"] = warnings, warnings
        return result

    async def resolve(self, ticker, instrument_id=None, listing_id=None):
        await self.ensure_directory()
        identity = await run_in_threadpool(self.repository.resolve, ticker, instrument_id, listing_id)
        return self._with_freshness(identity)
