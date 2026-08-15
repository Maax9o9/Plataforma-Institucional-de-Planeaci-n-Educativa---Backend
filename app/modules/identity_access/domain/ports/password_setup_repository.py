"""Puerto de tokens de un solo uso para configurar contrasena."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID


class PasswordSetupTokenStore(Protocol):
    async def issue(
        self,
        *,
        user_id: int,
        token_hash: str,
        expires_at: datetime,
    ) -> UUID: ...

    async def consume(self, token_hash: str) -> int | None: ...

    async def is_valid(self, token_hash: str) -> bool: ...
