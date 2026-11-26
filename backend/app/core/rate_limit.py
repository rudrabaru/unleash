"""
A per-client limit on how often an expensive or state-creating endpoint may be called.

In-process and in memory: the backend is one process (no workers to share state with). Each limiter
keeps, per client, the times of its recent calls inside a sliding window; a call over the limit is
refused with 429 and a Retry-After header. The limit is read from settings on every call, so a
changed setting applies at once and 0 turns the limiter off.
"""
import math
import threading
import time
from collections import deque
from typing import Callable, Deque, Dict, Optional

from fastapi import HTTPException, Request, status

from app.core.config import settings

WINDOW_SECONDS = 60.0
# Clients remembered at once; past this, clients whose window is empty are forgotten first.
MAX_TRACKED_CLIENTS = 10_000


def client_key(request: Request) -> str:
    """Who is calling: the connecting address, or the first X-Forwarded-For entry behind a trusted proxy."""
    if settings.TRUST_FORWARDED_FOR:
        forwarded = request.headers.get("x-forwarded-for", "")
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


class SlidingWindowLimiter:
    def __init__(self, limit: Callable[[], int], window_seconds: float = WINDOW_SECONDS) -> None:
        self._limit = limit
        self._window = window_seconds
        self._calls: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def retry_after(self, key: str, now: Optional[float] = None) -> Optional[float]:
        """Record one call by `key`. None when it is allowed, else the seconds until it would be."""
        limit = self._limit()
        if limit <= 0:
            return None
        now = time.monotonic() if now is None else now
        with self._lock:
            calls = self._calls.setdefault(key, deque())
            while calls and now - calls[0] >= self._window:
                calls.popleft()
            if len(calls) >= limit:
                return self._window - (now - calls[0])
            calls.append(now)
            if len(self._calls) > MAX_TRACKED_CLIENTS:
                self._forget_idle(now)
            return None

    def _forget_idle(self, now: float) -> None:
        for key in [k for k, calls in self._calls.items() if not calls or now - calls[-1] >= self._window]:
            del self._calls[key]

    def reset(self) -> None:
        with self._lock:
            self._calls.clear()

    def dependency(self, request: Request) -> None:
        """FastAPI dependency: refuse the request with 429 when its client is over the limit."""
        wait = self.retry_after(client_key(request))
        if wait is not None:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many attempts from this connection. Please wait a minute and try again.",
                headers={"Retry-After": str(max(1, math.ceil(wait)))},
            )


session_limiter = SlidingWindowLimiter(lambda: settings.RATE_LIMIT_PER_MINUTE)
submit_limiter = SlidingWindowLimiter(lambda: settings.RATE_LIMIT_PER_MINUTE)
