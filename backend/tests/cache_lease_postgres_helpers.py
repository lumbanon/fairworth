"""Real PostgreSQL row-lock regression, used only by guarded *_test tests."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import threading
import time

from sqlalchemy import event, text, update

from app.core.database import utcnow
from app.models import CacheEntry
from app.services.cache_service import CacheService


def renewal_sweep_race(factory, engine):
    cache = CacheService(factory)
    key = cache._lease_key("renewal-sweep-race")
    cache._write(key, {"owner": "renewed-owner"}, 1, "fairworth-cache-lease", utcnow() - timedelta(seconds=5))
    started = threading.Event()
    worker_pid = []
    def before_cursor(connection, _cursor, statement, _parameters, _context, _executemany):
        if statement.startswith("DELETE FROM cache_entries") and "IN (SELECT" in statement:
            worker_pid.append(connection.connection.driver_connection.info.backend_pid)
            started.set()
    event.listen(engine, "before_cursor_execute", before_cursor)
    try:
        with engine.connect() as renewal:
            transaction = renewal.begin()
            renewal.execute(update(CacheEntry).where(CacheEntry.key == key).values(expires_at=utcnow() + timedelta(minutes=1)))
            with ThreadPoolExecutor(max_workers=1) as workers:
                future = workers.submit(cache._acquire_lease, "sweep-new-key", "new-owner")
                try:
                    assert started.wait(3), "The expired-lease sweep did not start."
                    deadline = time.monotonic() + 3
                    blocked = False
                    with engine.connect() as observer:
                        while time.monotonic() < deadline:
                            blocked = bool(observer.execute(text("SELECT cardinality(pg_blocking_pids(:pid)) > 0"), {"pid": worker_pid[0]}).scalar_one())
                            if blocked:
                                break
                            time.sleep(.01)
                    assert blocked, "The regression requires the sweep to wait behind a renewal row lock."
                finally:
                    # The owner commits its renewal while DELETE is waiting.
                    transaction.commit()
                assert future.result(timeout=5)
        assert cache._read(key).payload == {"owner": "renewed-owner"}, "A renewed live lease must survive the stale sweep snapshot."
        cache._release_lease("renewal-sweep-race", "renewed-owner")
        cache._release_lease("sweep-new-key", "new-owner")
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor)
