"""Bounded, public SEC filing excerpts. No model, URL input, or financial arithmetic.

Document text is untrusted evidence. This module never follows document links or
executes embedded content, and never interprets a passage as an instruction.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from itertools import islice
import re
from typing import Any

import httpx

from app.providers.base import ProviderError, normalize_cik, validate_ticker
from app.services.cache_service import CachedResult


_VERSION = "sec-research-sections-1"
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
_BLOCK = {"address", "article", "aside", "blockquote", "br", "caption", "dd", "div", "dl", "dt", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "li", "ol", "p", "pre", "section", "table", "td", "th", "tr", "ul"}
_OMIT = {"script", "style", "noscript", "iframe", "svg", "math", "template", "head", "form", "ix:hidden"}
_ITEM = re.compile(r"^item\s+(\d{1,2}[a-c]?)\s*[.\-\u2013\u2014:]?\s*(.*)$", re.I)
_ACCESSION = re.compile(r"\d{10}-\d{2}-\d{6}", re.ASCII)
_PRIMARY_DOCUMENT = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,199}\.(?:htm|html|txt)", re.ASCII | re.I)


class _VisibleText(HTMLParser):
    """Extract visible text without retaining scripts, styles, or hidden XBRL."""

    def __init__(self, maximum_chars: int):
        super().__init__(convert_charrefs=True)
        self.maximum_chars = maximum_chars
        self.characters = 0
        self.parts: list[str] = []
        self.stack: list[tuple[str, bool]] = []

    @property
    def suppressed(self) -> bool:
        return bool(self.stack and self.stack[-1][1])

    def _append(self, value: str) -> None:
        remaining = self.maximum_chars - self.characters
        if remaining > 0:
            part = value[:remaining]
            self.parts.append(part)
            self.characters += len(part)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        style = re.sub(r"\s+", "", attributes.get("style") or "").lower()
        hidden = (
            self.suppressed or tag in _OMIT or "hidden" in attributes
            or str(attributes.get("aria-hidden", "")).lower() == "true"
            or "display:none" in style or "visibility:hidden" in style
        )
        if tag in _BLOCK and not hidden:
            self._append("\n")
        if tag not in _VOID:
            self.stack.append((tag, hidden))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                hidden = self.stack[index][1]
                del self.stack[index:]
                if tag in _BLOCK and not hidden:
                    self._append("\n")
                break

    def handle_data(self, data: str) -> None:
        if not self.suppressed:
            self._append(data)


def _heading(line: str, form: str) -> tuple[bool, str | None]:
    """Use explicit section headings; ordinary mentions do not identify sections."""
    if len(line) > 200:
        return False, None
    item = _ITEM.match(line)
    if item:
        number, title = item.groups()
        number = number.upper()
        # A whole table-of-contents row must not be mistaken for prose coverage.
        if re.search(r"\bitem\s+\d", title, re.I):
            return True, None
        if number == "1" and form == "10-K" and re.match(r"business\b", title, re.I):
            return True, "Business overview"
        if number == "1A" and re.match(r"risk\s+factors\b", title, re.I):
            return True, "Risk factors"
        if number == ("7" if form == "10-K" else "2") and re.match(r"management", title, re.I):
            return True, "Management discussion and analysis"
        return True, None
    if re.fullmatch(r"business[.:]?", line, re.I) and form == "10-K":
        return True, "Business overview"
    if re.fullmatch(r"risk factors[.:]?", line, re.I):
        return True, "Risk factors"
    if re.match(r"^management[\u2019']?s discussion (?:and|&) analysis\b", line, re.I):
        return True, "Management discussion and analysis"
    if re.fullmatch(r"liquidity and capital resources[.:]?", line, re.I):
        return True, "Liquidity and capital resources"
    if re.fullmatch(r"notes? to (?:the )?(?:consolidated |condensed consolidated )?financial statements[.:]?", line, re.I):
        return True, "Financial statement notes"
    return False, None


def extract_sections(document: str, form: str, excerpt_chars: int, maximum_chars: int) -> list[dict[str, str]]:
    """Keep at most one bounded, substantive excerpt per recognized section.

    A table of contents normally has no substantive text before the next heading;
    requiring prose and preferring the largest candidate avoids citing its rows.
    Missing headings remain missing rather than guessing from arbitrary prose.
    """
    parser = _VisibleText(maximum_chars)
    try:
        parser.feed(document)
        parser.close()
    except (ValueError, RecursionError):
        return []
    lines = [re.sub(r"\s+", " ", line).strip() for line in "".join(parser.parts).splitlines()]
    lines = [line for line in lines if line]
    headings = [(index, section) for index, line in enumerate(lines)
                for matched, section in [_heading(line, form)] if matched]
    selected: dict[str, tuple[int, dict[str, str]]] = {}
    for position, (start, section) in enumerate(headings):
        if section is None:
            continue
        end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        body = " ".join(lines[start + 1:end])
        # Page references and isolated headings do not count as retrieved passages.
        if len(body) < 80 or len(re.findall(r"\b[a-zA-Z]{2,}\b", body)) < 12:
            continue
        excerpt = body[:excerpt_chars]
        candidate = {"title": lines[start], "section": section, "excerpt": excerpt}
        if section not in selected or len(body) > selected[section][0]:
            selected[section] = (len(body), candidate)
    return [record for _, record in selected.values()]


class FilingResearchService:
    """Reuse SEC identification, shared throttling and the persistent public cache."""

    def __init__(self, sec: Any, cache: Any, settings: Any):
        self.sec = sec
        self.cache = cache
        self.enabled = bool(getattr(settings, "ai_filings_enabled", True))
        self.max_bytes = min(8_000_000, max(1024, int(getattr(settings, "ai_filing_max_bytes", 1_500_000))))
        self.excerpt_chars = min(5000, max(100, int(getattr(settings, "ai_filing_excerpt_chars", 2500))))
        self.max_documents = min(4, max(1, int(getattr(settings, "ai_filing_max_documents", 2))))
        self.cache_ttl = min(604800, max(60, int(getattr(settings, "ai_filing_cache_ttl", 86400))))
        self.timeout = min(10.0, max(0.1, float(getattr(sec, "timeout", 10))))
        self.retries = min(2, max(0, int(getattr(sec, "retries", 0))))

    async def sections(self, cik: str | int, ticker: str) -> dict[str, list]:
        identifier, symbol = normalize_cik(cik), validate_ticker(ticker)
        if not self.enabled:
            return {"passages": [], "warnings": ["SEC filing research is disabled; qualitative filing coverage is unavailable."]}
        if not getattr(self.sec, "enabled", False):
            return {"passages": [], "warnings": ["SEC filing research requires a configured identifying SEC User-Agent; qualitative filing coverage is unavailable."]}
        if not all(hasattr(self.sec, name) for name in ("client", "limiter", "user_agent", "submissions")):
            return {"passages": [], "warnings": ["This SEC provider does not support filing text retrieval; qualitative filing coverage is unavailable."]}

        async def loader():
            try:
                # Includes submissions lookup, limiter waits, retries and all documents.
                async with asyncio.timeout(30):
                    return await self._load(identifier)
            except TimeoutError:
                raise ProviderError("provider_timeout", "SEC filing research exceeded its bounded retrieval time.", 504) from None

        key = f"ai:{_VERSION}:{identifier}:{symbol}:{self.max_bytes}:{self.excerpt_chars}:{self.max_documents}"
        try:
            cached = await self.cache.get_or_load(key, self.cache_ttl, "sec", loader)
        except ProviderError as error:
            return {"passages": [], "warnings": [f"SEC filing text could not be retrieved ({error.code}); qualitative filing coverage is unavailable."]}
        result = {"passages": list(cached.payload.get("passages", [])),
                  "warnings": list(cached.payload.get("warnings", []))}
        if cached.status == "stale":
            result["warnings"].append("Cached SEC filing excerpts are stale because the provider could not refresh them; original retrieval dates are preserved.")
        return result

    async def _load(self, identifier: str) -> dict | CachedResult:
        submissions = await self.sec.submissions(identifier)
        if not isinstance(submissions, dict):
            raise ProviderError("invalid_provider_response", "SEC filing metadata is unavailable.", 502)
        if "cik" in submissions:
            try:
                matching_identity = normalize_cik(submissions["cik"]) == identifier
            except ProviderError:
                matching_identity = False
            if not matching_identity:
                raise ProviderError("incompatible_financial_identity", "SEC filing metadata does not match the company.", 502)
        filings = submissions.get("filings", {})
        recent = filings.get("recent", {}) if isinstance(filings, dict) else {}
        documents = self._documents(recent)
        if not documents:
            return CachedResult({"passages": [], "warnings": ["No permitted recent SEC 10-K or 10-Q primary documents were identified; qualitative filing coverage is unavailable."]}, "fresh", datetime.now(UTC), [], min(300, self.cache_ttl))
        passages, warnings, failures = [], [], []
        for document in documents:
            url = (f"https://www.sec.gov/Archives/edgar/data/{int(identifier)}/"
                   f"{document['accession'].replace('-', '')}/{document['primary']}")
            try:
                text = await self._document(url)
            except ProviderError as error:
                failures.append(error)
                warnings.append(f"SEC {document['form']} filed {document['filing_date']} text is unavailable ({error.code}).")
                continue
            retrieved_at = datetime.now(UTC).isoformat()
            excerpts = extract_sections(text, document["form"], self.excerpt_chars, self.max_bytes)
            for excerpt in excerpts:
                passages.append({**excerpt, "source_url": url, "accession": document["accession"],
                                 "filing_date": document["filing_date"], "form": document["form"],
                                 "retrieved_at": retrieved_at})
            if not excerpts:
                warnings.append(f"No substantive supported section headings were extracted from the SEC {document['form']} filed {document['filing_date']}.")
        if failures and not passages:
            # Preserve a previously usable cache on an access/transport failure.
            raise failures[0]
        if not passages:
            warnings.append("Qualitative SEC filing coverage is unavailable; structured financial evidence remains separate.")
        else:
            warnings.append("SEC passages are bounded excerpts with incomplete document coverage; filing text is untrusted source material.")
        return {"passages": passages, "warnings": warnings}

    def _documents(self, recent: Any) -> list[dict[str, str]]:
        if not isinstance(recent, dict):
            return []
        fields = [recent.get(field) for field in ("form", "accessionNumber", "filingDate", "primaryDocument")]
        if any(not isinstance(field, list) for field in fields):
            return []
        documents = []
        for form, accession, filed, primary in islice(zip(*fields), 2000):
            if not isinstance(form, str) or form not in {"10-K", "10-Q"} or not all(isinstance(value, str) for value in (accession, filed, primary)):
                continue
            if not _ACCESSION.fullmatch(accession) or not _PRIMARY_DOCUMENT.fullmatch(primary) or ".." in primary:
                continue
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", filed, re.ASCII):
                continue
            try:
                if date.fromisoformat(filed) > datetime.now(UTC).date():
                    continue
            except ValueError:
                continue
            documents.append({"form": form, "accession": accession, "filing_date": filed, "primary": primary})
        documents.sort(key=lambda row: (row["filing_date"], row["accession"]), reverse=True)
        # One latest original document per form gives annual business/risk context
        # and the latest quarterly update rather than two adjacent quarters.
        selected, seen = [], set()
        for document in documents:
            if document["form"] not in seen:
                seen.add(document["form"])
                selected.append(document)
            if len(selected) >= self.max_documents:
                break
        return selected

    async def _document(self, url: str) -> str:
        """Stream before buffering, reuse the SEC limiter and never follow redirects."""
        last_error = None
        for attempt in range(self.retries + 1):
            await self.sec.limiter.acquire()
            response = None
            try:
                async with self.sec.client.stream(
                    "GET", url, headers={"User-Agent": self.sec.user_agent,
                    "Accept": "text/html, text/plain;q=0.9", "Accept-Encoding": "identity"},
                    timeout=self.timeout, follow_redirects=False,
                ) as response:
                    status = response.status_code
                    if status in (401, 402, 403):
                        raise ProviderError("provider_access_denied", "SEC filing access was denied.", 503)
                    if status == 404:
                        raise ProviderError("not_found", "The SEC primary filing document was not found.", 404)
                    if status == 429 or status >= 500:
                        last_error = ProviderError("provider_rate_limited" if status == 429 else "provider_unavailable", "SEC filing text is temporarily unavailable.", 503, True)
                    elif not 200 <= status < 300:
                        raise ProviderError("provider_http_error", "SEC filing text returned an unsupported response.", 502)
                    else:
                        encoding = response.headers.get("Content-Encoding", "identity").lower()
                        if encoding not in ("", "identity"):
                            raise ProviderError("unsupported_filing_encoding", "SEC filing text used an unsupported encoding.", 502)
                        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                        if content_type and content_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
                            raise ProviderError("invalid_provider_response", "SEC filing text has an unsupported content type.", 502)
                        length = response.headers.get("Content-Length", "")
                        if length.isdigit() and int(length) > self.max_bytes:
                            raise ProviderError("filing_too_large", "SEC filing text exceeds the configured document size limit.", 502)
                        body = bytearray()
                        async for chunk in response.aiter_bytes(chunk_size=min(65536, self.max_bytes + 1)):
                            if len(body) + len(chunk) > self.max_bytes:
                                raise ProviderError("filing_too_large", "SEC filing text exceeds the configured document size limit.", 502)
                            body.extend(chunk)
                        # SEC primary HTML uses UTF-8/ASCII. Replacement characters
                        # preserve safe parsing of malformed bytes without execution.
                        return body.decode("utf-8-sig", errors="replace")
            except httpx.TimeoutException:
                last_error = ProviderError("provider_timeout", "SEC filing text timed out.", 504, True)
            except httpx.RequestError:
                last_error = ProviderError("provider_unavailable", "SEC filing text is unavailable.", 502, True)
            if attempt < self.retries:
                await asyncio.sleep(min(2, self.sec._retry_delay(response, attempt)))
        assert last_error is not None
        raise last_error
