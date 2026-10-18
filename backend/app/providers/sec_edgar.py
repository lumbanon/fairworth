"""Official SEC submissions, company-facts, and ticker directory adapters.

References:
https://www.sec.gov/search-filings/edgar-application-programming-interfaces
https://www.sec.gov/about/developer-resources
"""

from __future__ import annotations

import asyncio
import re
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from app.providers.base import JsonHttpProvider, ProviderError, normalize_cik, validate_ticker


class SecEdgarProvider(JsonHttpProvider):
    name = "sec"
    TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
    EXCHANGE_TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
    DATA_ORIGIN = "https://data.sec.gov"

    def __init__(
        self,
        client: httpx.AsyncClient,
        user_agent: str,
        min_interval: float = 0.2,
        retries: int = 2,
        timeout: float = 20,
        ticker_cache_seconds: int = 86400,
    ) -> None:
        # SEC's cap applies to the operator across all machines. Use one worker
        # locally and keep a configurable margin below ten requests/second.
        super().__init__(
            client, min_interval=max(0.1, min_interval), retries=retries, timeout=timeout
        )
        self.user_agent = user_agent.strip()
        self.enabled = bool(
            re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", self.user_agent, re.I)
        ) and "\n" not in self.user_agent and "\r" not in self.user_agent
        self.ticker_cache_seconds = max(60, ticker_cache_seconds)
        self._tickers: list[dict[str, Any]] | None = None
        self._ticker_cache_at = 0.0
        self._ticker_lock = asyncio.Lock()

    async def _sec_json(self, url: str) -> dict:
        if not self.enabled:
            raise ProviderError(
                "provider_disabled",
                "SEC access requires an identifying User-Agent with configured contact information.",
                503,
            )
        result = await self._json(
            url,
            headers={"User-Agent": self.user_agent, "Accept": "application/json"},
        )
        if not isinstance(result, dict):
            raise ProviderError("invalid_provider_response", "SEC returned an unexpected response.", 502)
        return result

    async def _directory(self) -> list[dict[str, Any]]:
        async with self._ticker_lock:
            if self._tickers is not None and time.monotonic() - self._ticker_cache_at < self.ticker_cache_seconds:
                return self._tickers
            raw = await self._sec_json(self.TICKERS_URL)
            entries = []
            for record in raw.values():
                if not isinstance(record, dict):
                    continue
                try:
                    ticker = validate_ticker(record.get("ticker", ""))
                    cik = normalize_cik(record.get("cik_str", ""))
                except ProviderError:
                    continue
                if not record.get("title"):
                    continue
                entries.append(
                    {"ticker": ticker, "name": str(record["title"]), "cik": cik, "exchange": None}
                )
            if not entries:
                raise ProviderError("invalid_provider_response", "The SEC ticker directory is unavailable.", 502)
            self._tickers = entries
            self._ticker_cache_at = time.monotonic()
            return entries

    async def search(self, q: str, limit: int = 10) -> list[dict[str, Any]]:
        query = q.strip().upper()[:100]
        if not query:
            return []
        directory = await self._directory()
        alias = query.replace(".", "-")
        matches = [
            row for row in directory
            if query in row["ticker"] or query in row["name"].upper() or alias == row["ticker"]
        ]
        matches.sort(
            key=lambda row: (
                row["ticker"] not in (query, alias),
                not row["ticker"].startswith(query),
                row["ticker"],
            )
        )
        return matches[: min(50, max(1, limit))]

    async def security_directory(self):
        """Acquire registrant references, never infer an actively listed universe."""
        from app.registry.importers import sec_reference_records
        raw = await self._sec_json(self.EXCHANGE_TICKERS_URL)
        records = sec_reference_records(raw, source_url=self.EXCHANGE_TICKERS_URL)
        if not records:
            raise ProviderError("invalid_provider_response", "The SEC exchange reference contains no usable records.", 502)
        now = datetime.now(UTC)
        return {"records": records, "provenance": {"source": "sec-edgar-reference", "as_of": now.date().isoformat(),
                "retrieved_at": now.isoformat(), "source_url": self.EXCHANGE_TICKERS_URL,
                "complete_scope": False, "scope": "SEC registrant/ticker references, not a verified actively listed equity universe.",
                "rights": "Official SEC reference data; access remains subject to SEC fair-access requirements.",
                "version": "sec-exchange-reference-1"}}

    async def company(self, ticker: str) -> dict[str, Any]:
        symbol = validate_ticker(ticker)
        alias = symbol.replace(".", "-")
        row = next(
            (item for item in await self._directory() if item["ticker"] in (symbol, alias)),
            None,
        )
        if row is None:
            raise ProviderError("unsupported_ticker", "This ticker is not present in the SEC company directory.", 404)
        filing = await self.submissions(row["cik"])
        tickers = filing.get("tickers")
        tickers = tickers if isinstance(tickers, list) else []
        exchanges = filing.get("exchanges")
        exchanges = exchanges if isinstance(exchanges, list) else []
        index = tickers.index(row["ticker"]) if row["ticker"] in tickers else None
        exchange = exchanges[index] if index is not None and index < len(exchanges) else None
        listed_symbols = {
            symbol.strip().upper().replace(".", "-")
            for symbol in tickers if isinstance(symbol, str) and symbol.strip()
        }
        multiple_classes = len(listed_symbols) > 1 if listed_symbols else None
        warnings = []
        if multiple_classes:
            warnings.append({
                "field": "shares",
                "code": "share_class_basis_unverified",
                "message": "SEC company-level facts cover multiple listed share classes. A ticker-specific per-share basis has not been verified; no share-count or EPS rescaling was invented.",
            })
        return {
            **row,
            "name": filing.get("name") or row["name"],
            "exchange": exchange,
            "sector": None,
            "industry": filing.get("sicDescription") or None,
            "description": filing.get("description") or None,
            "sic": str(filing["sic"]) if filing.get("sic") else None,
            "currency": None,
            "provider": self.name,
            "has_multiple_share_classes": multiple_classes,
            "share_class_basis_verified": False,
            "warnings": warnings,
        }

    async def facts(self, cik: str | int) -> dict:
        identifier = normalize_cik(cik)
        payload = await self._sec_json(f"{self.DATA_ORIGIN}/api/xbrl/companyfacts/CIK{identifier}.json")
        if not isinstance(payload.get("facts"), dict):
            raise ProviderError("invalid_provider_response", "SEC company facts are unavailable.", 502)
        if "cik" in payload:
            try:
                matching_identity = normalize_cik(payload["cik"]) == identifier
            except ProviderError:
                matching_identity = False
            if not matching_identity:
                raise ProviderError("incompatible_financial_identity", "SEC facts do not match the requested company identifier.", 502)
        return payload

    async def submissions(self, cik: str | int) -> dict:
        identifier = normalize_cik(cik)
        result = await self._sec_json(f"{self.DATA_ORIGIN}/submissions/CIK{identifier}.json")
        if result.get("cik") is not None:
            try:
                matches = normalize_cik(result["cik"]) == identifier
            except ProviderError:
                matches = False
            if not matches:
                raise ProviderError("incompatible_financial_identity", "SEC submissions do not match the selected issuer.", 502)
        return result

    async def company_for_identity(self, identity: dict) -> dict:
        """Enrich an already resolved instrument without resolving its symbol again."""
        filing = await self.submissions(identity["cik"])
        if filing.get("cik") is None:
            raise ProviderError("incompatible_financial_identity", "SEC submissions omit the issuer identifier required for the selected security.", 502)
        tickers = filing.get("tickers") if isinstance(filing.get("tickers"), list) else []
        exchanges = filing.get("exchanges") if isinstance(filing.get("exchanges"), list) else []
        permitted = {identity["ticker"]}
        for alias in identity.get("symbol_aliases", []):
            value = alias.get("symbol", alias.get("alias")) if isinstance(alias, dict) else alias
            if isinstance(value, str):
                permitted.add(value)
        symbols = identity.get("provider_symbols") or {}
        if isinstance(symbols, dict):
            permitted.update(value for value in symbols.values() if isinstance(value, str))
        matches = [index for index, symbol in enumerate(tickers) if symbol in permitted]
        if tickers and not matches and identity.get("listing_status") == "active":
            raise ProviderError("incompatible_security_identity", "SEC listed symbols do not match the resolved security.", 502)
        index = matches[0] if matches else None
        exchange = exchanges[index] if index is not None and index < len(exchanges) else identity.get("exchange")
        warnings = []
        if len(tickers) > 1:
            warnings.append({"field": "shares", "code": "share_class_basis_unverified",
                             "message": "SEC issuer facts cover multiple listed securities; a class-specific share and EPS basis must be verified."})
        return {**identity, "name": filing.get("name") or identity["name"], "exchange": exchange,
                "sector": None, "industry": filing.get("sicDescription") or None,
                "description": filing.get("description") or None, "sic": str(filing["sic"]) if filing.get("sic") else None,
                "currency": None, "provider": self.name,
                "has_multiple_share_classes": len(tickers) > 1 if tickers else None,
                "share_class_basis_verified": False, "warnings": warnings}
