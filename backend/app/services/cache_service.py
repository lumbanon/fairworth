import asyncio
from dataclasses import dataclass
from datetime import timedelta

from fastapi.encoders import jsonable_encoder

from app.core.database import as_utc, utcnow
from app.models import CacheEntry
from app.providers.base import ProviderError


@dataclass
class CachedResult:
    payload: dict | list
    status: str
    retrieved_at: object
    warnings: list
    cache_ttl_seconds: int | None = None


class CacheService:
    """Persistent TTL cache, including an explicit stale-on-provider-failure path."""

    def __init__(self, session_factory):
        self.session_factory = session_factory
        self._locks = {}

    def _read(self, key):
        with self.session_factory() as session:
            return session.get(CacheEntry, key)

    def _write(self, key, payload, ttl, provider, retrieved_at=None):
        now = as_utc(retrieved_at) if retrieved_at is not None else utcnow()
        with self.session_factory.begin() as session:
            session.merge(CacheEntry(key=key, payload=jsonable_encoder(payload), retrieved_at=now,
                                     expires_at=now + timedelta(seconds=ttl), provider=provider))
        return now

    async def get_or_load(self, key, ttl, provider, loader):
        # A service instance is shared by all requests in this process.
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            entry = self._read(key)
            if entry and as_utc(entry.expires_at) > utcnow():
                return CachedResult(entry.payload, "fresh", as_utc(entry.retrieved_at), [])
            try:
                payload = await loader()
            except ProviderError as error:
                if not entry:
                    raise
                warning = {"field": provider, "code": "stale_provider_failure",
                           "message": f"Cached {provider} data is stale because the provider could not refresh it ({error.code})."}
                return CachedResult(entry.payload, "stale", as_utc(entry.retrieved_at), [warning])
            if isinstance(payload, CachedResult):
                # Derived caches keep the original upstream retrieval instant.
                # A stale shared source must not become a freshly cached snapshot.
                if payload.status == "stale":
                    return payload
                effective_ttl = min(ttl, max(1, payload.cache_ttl_seconds)) if payload.cache_ttl_seconds is not None else ttl
                retrieved_at = self._write(key, payload.payload, effective_ttl, provider, payload.retrieved_at)
                return CachedResult(payload.payload, payload.status, retrieved_at, payload.warnings)
            retrieved_at = self._write(key, payload, ttl, provider)
            return CachedResult(payload, "fresh", retrieved_at, [])
