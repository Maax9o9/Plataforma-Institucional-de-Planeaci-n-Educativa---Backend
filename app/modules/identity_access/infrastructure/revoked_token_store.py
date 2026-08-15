"""Blacklist temporal en memoria para access tokens."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID


class InMemoryRevokedTokenStore:
    def __init__(self) -> None:
        self._tokens: dict[UUID, datetime] = {}
        self._lock = asyncio.Lock()

    async def revoke(self, token_id: UUID, expires_at: datetime) -> None:
        if expires_at <= datetime.now(UTC):
            return
        async with self._lock:
            self._tokens[token_id] = expires_at

    async def is_revoked(self, token_id: UUID) -> bool:
        now = datetime.now(UTC)
        async with self._lock:
            expires_at = self._tokens.get(token_id)
            if expires_at is None:
                return False
            if expires_at <= now:
                del self._tokens[token_id]
                return False
            return True
