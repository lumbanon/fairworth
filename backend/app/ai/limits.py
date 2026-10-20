"""Per-process client/IP budgets and fail-fast generation admission."""
from collections import OrderedDict, deque
from contextlib import asynccontextmanager
import hashlib
import re
import time
from app.core.exceptions import ApiError


class UsageLimits:
    def __init__(self, settings, clock=time.monotonic):
        self.settings, self.clock = settings, clock
        self.clients = OrderedDict()
        self.daily = deque()
        self.active = 0

    def identity(self, session, address):
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,100}", session or ""):
            raise ApiError("ai_session_required", "A valid browser research session is required.", 400)
        # Ignore forwarding headers. A trusted reverse proxy must enforce edge limits.
        return hashlib.sha256((address + "\0" + session).encode()).hexdigest()

    def throttle(self, identity, address):
        now = self.clock()
        for key in list(self.clients):
            if not self.clients[key] or self.clients[key][-1] <= now - 3600:
                self.clients.pop(key)
        # IP budget prevents trivial session-ID rotation bypassing client limits.
        keys = (identity, "ip:" + hashlib.sha256(address.encode()).hexdigest())
        if len(self.clients) + sum(key not in self.clients for key in keys) > 4096:
            raise ApiError("ai_capacity", "Research request capacity is temporarily unavailable.", 503)
        for key in keys:
            events = self.clients.get(key, deque())
            while events and events[0] <= now - 3600:
                events.popleft()
            if len(events) >= self.settings.ai_client_requests_per_hour or sum(x > now - 60 for x in events) >= self.settings.ai_client_requests_per_minute:
                raise ApiError("ai_rate_limited", "Research request limit reached. Please try again later.", 429)
        for key in keys:
            events = self.clients.setdefault(key, deque())
            events.append(now)
            self.clients.move_to_end(key)

    @asynccontextmanager
    async def admission(self):
        if self.active >= self.settings.ai_max_concurrent_requests:
            raise ApiError("ai_busy", "Research is busy. Please try again shortly.", 429)
        self.active += 1
        try:
            yield
        finally:
            self.active -= 1

    def generation(self):
        now = self.clock()
        while self.daily and self.daily[0] <= now - 86400:
            self.daily.popleft()
        if len(self.daily) >= self.settings.ai_global_generations_per_day:
            raise ApiError("ai_daily_limit", "The server's daily AI generation limit has been reached.", 429)
        self.daily.append(now)
