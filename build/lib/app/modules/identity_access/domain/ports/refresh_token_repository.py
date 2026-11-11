"""Contrato del almacenamiento de refresh tokens rotables."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class RefreshTokenRecord:
    token_id: UUID
    user_id: int
    session_id: UUID
    expires_at: datetime
    active: bool


class RefreshTokenStore(Protocol):
    async def save(
        self,
        *,
        token: str,
        token_id: UUID,
        user_id: int,
        session_id: UUID,
        expires_at: datetime,
    ) -> None: ...

    async def consume(self, *, token: str, token_id: UUID) -> RefreshTokenRecord | None: ...

    async def rotate(
        self,
        *,
        current_token: str,
        current_token_id: UUID,
        new_token: str,
        new_token_id: UUID,
        user_id: int,
        session_id: UUID,
        expires_at: datetime,
    ) -> RefreshTokenRecord | None: ...

    async def revoke(self, token_id: UUID) -> None: ...

    async def revoke_session(self, session_id: UUID) -> None: ...

    async def revoke_user(self, user_id: int) -> None: ...
