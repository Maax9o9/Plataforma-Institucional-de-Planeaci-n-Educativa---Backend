"""Limitador local y acotado para intentos fallidos de autenticacion."""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from time import monotonic


class LoginRateLimiter:
    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    def _discard_expired(self, failures: deque[float], now: float) -> None:
        threshold = now - self.window_seconds
        while failures and failures[0] <= threshold:
            failures.popleft()

    async def retry_after(self, key: str) -> int:
        async with self._lock:
            now = monotonic()
            failures = self._failures[key]
            self._discard_expired(failures, now)
            if len(failures) < self.max_attempts:
                return 0
            return max(1, int(self.window_seconds - (now - failures[0])))

    async def record_failure(self, key: str) -> None:
        async with self._lock:
            now = monotonic()
            failures = self._failures[key]
            self._discard_expired(failures, now)
            failures.append(now)

    async def clear(self, key: str) -> None:
        async with self._lock:
            self._failures.pop(key, None)
