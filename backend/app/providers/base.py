"""Shared, bounded HTTP access and safe provider errors."""

from __future__ import annotations

import asyncio
import re
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx


class ProviderError(Exception):
    """A public error message that never includes an upstream URL or API key."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 502,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable


def validate_ticker(ticker: str) -> str:
    normalized = str(ticker).strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", normalized, flags=re.ASCII):
        raise ProviderError("invalid_ticker", "Enter a valid US stock ticker.", 400)
    return normalized


def normalize_cik(cik: str | int) -> str:
    value = str(cik)
    if not value.isascii() or not value.isdigit() or len(value) > 10 or int(value) <= 0:
        raise ProviderError("invalid_cik", "The company identifier is invalid.", 400)
    return value.zfill(10)


class RateLimiter:
    """Serialize request starts across the shared provider instance."""

    def __init__(self, min_interval: float) -> None:
        self.min_interval = max(0.0, float(min_interval))
        self._last_started: float | None = None
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            if self._last_started is not None:
                delay = self.min_interval - (now - self._last_started)
                if delay > 0:
                    await asyncio.sleep(delay)
            self._last_started = time.monotonic()


class JsonHttpProvider:
    """Reuse an injected client, retry transient failures, and reject redirects."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        min_interval: float = 0.2,
        retries: int = 2,
        timeout: float = 20,
    ) -> None:
        self.client = client
        self.limiter = RateLimiter(min_interval)
        self.retries = min(5, max(0, int(retries)))
        self.timeout = min(120.0, max(0.1, float(timeout)))

    @staticmethod
    def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    delay = float(retry_after)
                except ValueError:
                    try:
                        delay = (
                            parsedate_to_datetime(retry_after) - datetime.now(UTC)
                        ).total_seconds()
                    except (TypeError, ValueError, OverflowError):
                        delay = 0.0
                return min(30.0, max(0.0, delay))
        return min(8.0, 0.5 * (2**attempt))

    async def _json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        last_error: ProviderError | None = None
        for attempt in range(self.retries + 1):
            await self.limiter.acquire()
            response = None
            try:
                response = await self.client.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout,
                    follow_redirects=False,
                )
            except httpx.TimeoutException:
                last_error = ProviderError(
                    "provider_timeout", "The financial data provider timed out.", 504, True
                )
            except httpx.RequestError:
                last_error = ProviderError(
                    "provider_unavailable", "The financial data provider is unavailable.", 502, True
                )
            else:
                status = response.status_code
                if status == 404:
                    raise ProviderError("not_found", "The requested provider data was not found.", 404)
                if status == 402:
                    raise ProviderError(
                        "provider_subscription_required",
                        "This provider endpoint is not available for this ticker under the configured subscription.",
                        503,
                    )
                if status in (401, 403):
                    raise ProviderError(
                        "provider_access_denied",
                        "The financial data provider denied access. Check provider configuration and permissions.",
                        503,
                    )
                if status == 429 or status >= 500:
                    last_error = ProviderError(
                        "provider_rate_limited" if status == 429 else "provider_unavailable",
                        "The financial data provider rate limit was reached."
                        if status == 429
                        else "The financial data provider is temporarily unavailable.",
                        503 if status == 429 else 502,
                        True,
                    )
                elif not 200 <= status < 300:
                    raise ProviderError("provider_http_error", "The financial data provider returned an error.", 502)
                else:
                    try:
                        return response.json()
                    except (ValueError, UnicodeDecodeError):
                        raise ProviderError(
                            "invalid_provider_response", "The financial data provider returned invalid JSON.", 502
                        ) from None
            if attempt < self.retries:
                await asyncio.sleep(self._retry_delay(response, attempt))
        assert last_error is not None
        raise last_error
