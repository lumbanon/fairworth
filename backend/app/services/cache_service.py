import asyncio
from asyncio import sleep as pause
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import timedelta
import hashlib
import time
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy import delete, select, update

from app.core.database import as_utc, utcnow
from app.models import CacheEntry
from app.providers.base import ProviderError
from app.providers.permitted_use import require_public_data


@dataclass
class CachedResult:
    payload: dict | list
    status: str
    retrieved_at: object
    warnings: list
    cache_ttl_seconds: int | None = None
    expires_at: object | None = None


class CacheService:
    """Persistent TTL cache, including an explicit stale-on-provider-failure path."""

    def __init__(self, session_factory, *, lease_seconds=30, wait_seconds=30, poll_seconds=0.05):
        self.session_factory = session_factory
        self._locks = {}
        self._lock_users = {}
        self.lease_seconds = max(0.1, float(lease_seconds))
        self.wait_seconds = max(0.01, float(wait_seconds))
        self.poll_seconds = max(0.005, float(poll_seconds))

    @asynccontextmanager
    async def _key_lock(self, key):
        lock = self._locks.setdefault(key, asyncio.Lock())
        self._lock_users[key] = self._lock_users.get(key, 0) + 1
        acquired = False
        try:
            try:
                await asyncio.wait_for(lock.acquire(), timeout=self.wait_seconds)
                acquired = True
            except TimeoutError:
                pass
            yield acquired
        finally:
            if acquired:
                lock.release()
            self._lock_users[key] -= 1
            if self._lock_users[key] == 0:
                self._lock_users.pop(key, None)
                self._locks.pop(key, None)

    @staticmethod
    def _lease_key(key):
        return "fairworth:cache-load-lease:" + hashlib.sha256(key.encode()).hexdigest()

    def _acquire_lease(self, key, owner):
        now = utcnow()
        with self.session_factory.begin() as session:
            # Reclaim a bounded number of crashed coordination rows only.
            # Provider data, even expired data, remains available for fallback.
            expired = select(CacheEntry.key).where(CacheEntry.provider == "fairworth-cache-lease",
                                                   CacheEntry.expires_at <= now).limit(100)
            session.execute(delete(CacheEntry).where(CacheEntry.key.in_(expired),
                            CacheEntry.provider == "fairworth-cache-lease", CacheEntry.expires_at <= now)
                            .execution_options(synchronize_session=False))
            if session.bind.dialect.name == "postgresql":
                from sqlalchemy.dialects.postgresql import insert
            elif session.bind.dialect.name == "sqlite":
                from sqlalchemy.dialects.sqlite import insert
            else:
                raise RuntimeError("Cache leases require PostgreSQL or test SQLite.")
            values = {"key": self._lease_key(key), "payload": {"owner": owner}, "provider": "fairworth-cache-lease",
                      "retrieved_at": now, "expires_at": now + timedelta(seconds=self.lease_seconds)}
            statement = insert(CacheEntry).values(**values).on_conflict_do_update(
                index_elements=["key"], set_=values, where=CacheEntry.expires_at <= now).returning(CacheEntry.key)
            return session.execute(statement).scalar_one_or_none() is not None

    def _renew_lease(self, key, owner):
        with self.session_factory.begin() as session:
            result = session.execute(update(CacheEntry).where(CacheEntry.key == self._lease_key(key),
                CacheEntry.payload["owner"].as_string() == owner).values(expires_at=utcnow() + timedelta(seconds=self.lease_seconds)))
            return result.rowcount == 1

    def _release_lease(self, key, owner):
        with self.session_factory.begin() as session:
            session.execute(delete(CacheEntry).where(CacheEntry.key == self._lease_key(key),
                                                     CacheEntry.payload["owner"].as_string() == owner))

    async def _heartbeat(self, key, owner):
        while True:
            await pause(self.lease_seconds / 3)
            if not self._renew_lease(key, owner):
                raise ProviderError("cache_lease_lost", "The financial-data refresh ownership expired; retry after the active refresh completes.", 503, True)

    @staticmethod
    def _stale(entry, provider, error):
        warning = {"field": provider, "code": "stale_provider_failure",
                   "message": f"Cached {provider} data is stale because the provider could not refresh it ({error.code})."}
        return CachedResult(entry.payload, "stale", as_utc(entry.retrieved_at), [warning], expires_at=as_utc(entry.expires_at))

    def _read(self, key):
        with self.session_factory() as session:
            entry = session.get(CacheEntry, key)
            if entry:
                require_public_data(entry.payload, entry.provider)
            return entry

    def _read_fresh(self, key):
        with self.session_factory() as session:
            entry = session.scalar(select(CacheEntry).where(CacheEntry.key == key, CacheEntry.expires_at > utcnow()))
            if entry:
                require_public_data(entry.payload, entry.provider)
            return entry

    def _write(self, key, payload, ttl, provider, retrieved_at=None, *, owner=None):
        require_public_data(payload, provider)
        now = as_utc(retrieved_at) if retrieved_at is not None else utcnow()
        with self.session_factory.begin() as session:
            if owner is not None:
                if session.bind.dialect.name == "sqlite":
                    session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                lease = session.scalar(select(CacheEntry).where(CacheEntry.key == self._lease_key(key)).with_for_update())
                if not lease or lease.payload.get("owner") != owner or as_utc(lease.expires_at) <= utcnow():
                    raise ProviderError("cache_lease_lost", "The financial-data refresh ownership expired; no replacement snapshot was published.", 503, True)
            session.merge(CacheEntry(key=key, payload=jsonable_encoder(payload), retrieved_at=now,
                                     expires_at=now + timedelta(seconds=ttl), provider=provider))
        return now

    async def get_or_load(self, key, ttl, provider, loader):
        # Local locks have bounded lifetimes; DB leases coalesce independent
        # worker instances. No SQL transaction spans provider/network awaits.
        async with self._key_lock(key) as acquired:
            entry = self._read(key)
            if entry and as_utc(entry.expires_at) > utcnow():
                return CachedResult(entry.payload, "fresh", as_utc(entry.retrieved_at), [], expires_at=as_utc(entry.expires_at))
            if not acquired:
                error = ProviderError("cache_refresh_busy", "This financial-data snapshot is being refreshed. Retry shortly.", 503, True)
                if entry:
                    return self._stale(entry, provider, error)
                raise error
            owner = str(uuid4())
            deadline = time.monotonic() + self.wait_seconds
            while not self._acquire_lease(key, owner):
                refreshed = self._read_fresh(key)
                if refreshed:
                    return CachedResult(refreshed.payload, "fresh", as_utc(refreshed.retrieved_at), [], expires_at=as_utc(refreshed.expires_at))
                if time.monotonic() >= deadline:
                    error = ProviderError("cache_refresh_busy", "This financial-data snapshot is being refreshed. Retry shortly.", 503, True)
                    if entry:
                        return self._stale(entry, provider, error)
                    raise error
                await pause(min(self.poll_seconds, max(0, deadline - time.monotonic())))
            heartbeat = load_task = None
            try:
                # A previous owner may have published immediately before this
                # lease acquisition. Recheck while ownership is exclusive.
                entry = self._read(key)
                if entry and as_utc(entry.expires_at) > utcnow():
                    return CachedResult(entry.payload, "fresh", as_utc(entry.retrieved_at), [], expires_at=as_utc(entry.expires_at))
                heartbeat = asyncio.create_task(self._heartbeat(key, owner))
                load_task = asyncio.ensure_future(loader())
                completed, _ = await asyncio.wait((load_task, heartbeat), return_when=asyncio.FIRST_COMPLETED)
                if heartbeat in completed:
                    heartbeat.result()
                payload = load_task.result()
                if not self._renew_lease(key, owner):
                    raise ProviderError("cache_lease_lost", "The financial-data refresh ownership expired; no replacement snapshot was published.", 503, True)
                if isinstance(payload, CachedResult):
                    # Derived caches preserve original upstream retrieval age.
                    if payload.status == "stale":
                        return payload
                    effective_ttl = min(ttl, max(1, payload.cache_ttl_seconds)) if payload.cache_ttl_seconds is not None else ttl
                    retrieved_at = self._write(key, payload.payload, effective_ttl, provider, payload.retrieved_at, owner=owner)
                    expires_at = retrieved_at + timedelta(seconds=effective_ttl)
                    if payload.expires_at is not None:
                        expires_at = min(expires_at, as_utc(payload.expires_at))
                    return CachedResult(payload.payload, payload.status, retrieved_at, payload.warnings, expires_at=expires_at)
                retrieved_at = self._write(key, payload, ttl, provider, owner=owner)
                return CachedResult(payload, "fresh", retrieved_at, [], expires_at=retrieved_at + timedelta(seconds=ttl))
            except ProviderError as error:
                if not entry:
                    raise
                return self._stale(entry, provider, error)
            finally:
                for task in (load_task, heartbeat):
                    if task is not None:
                        if not task.done():
                            task.cancel()
                        with suppress(asyncio.CancelledError, Exception):
                            await task
                self._release_lease(key, owner)
