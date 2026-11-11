"""Contrato de blacklist temporal para access tokens."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID


class RevokedTokenStore(Protocol):
    async def revoke(self, token_id: UUID, expires_at: datetime) -> None: ...

    async def is_revoked(self, token_id: UUID) -> bool: ...
