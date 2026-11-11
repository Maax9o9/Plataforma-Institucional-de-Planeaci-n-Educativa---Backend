"""Almacenamiento temporal de refresh tokens con rotacion y deteccion de reuso."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

from ..domain.ports.refresh_token_repository import RefreshTokenRecord


@dataclass
class _StoredRefreshToken:
    token_hash: str
    record: RefreshTokenRecord


class InMemoryRefreshTokenStore:
    def __init__(self) -> None:
        self._tokens: dict[UUID, _StoredRefreshToken] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _hash(token: str) -> str:
        return sha256(token.encode("utf-8")).hexdigest()

    async def save(
        self,
        *,
        token: str,
        token_id: UUID,
        user_id: int,
        session_id: UUID,
        expires_at: datetime,
    ) -> None:
        record = RefreshTokenRecord(
            token_id=token_id,
            user_id=user_id,
            session_id=session_id,
            expires_at=expires_at,
            active=True,
        )
        async with self._lock:
            self._tokens[token_id] = _StoredRefreshToken(self._hash(token), record)

    async def consume(self, *, token: str, token_id: UUID) -> RefreshTokenRecord | None:
        async with self._lock:
            stored = self._tokens.get(token_id)
            if stored is None or stored.token_hash != self._hash(token):
                return None

            now = datetime.now(UTC)
            if not stored.record.active or stored.record.expires_at <= now:
                return RefreshTokenRecord(**{**stored.record.__dict__, "active": False})

            consumed = RefreshTokenRecord(**{**stored.record.__dict__, "active": False})
            self._tokens[token_id] = _StoredRefreshToken(stored.token_hash, consumed)
            return stored.record

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
    ) -> RefreshTokenRecord | None:
        async with self._lock:
            stored = self._tokens.get(current_token_id)
            if stored is None or stored.token_hash != self._hash(current_token):
                return None
            now = datetime.now(UTC)
            active = stored.record.active and stored.record.expires_at > now
            current = RefreshTokenRecord(**{**stored.record.__dict__, "active": active})
            self._tokens[current_token_id] = _StoredRefreshToken(
                stored.token_hash,
                RefreshTokenRecord(**{**stored.record.__dict__, "active": False}),
            )
            if not active:
                for token_id, candidate in list(self._tokens.items()):
                    if candidate.record.session_id == stored.record.session_id:
                        self._tokens[token_id] = _StoredRefreshToken(
                            candidate.token_hash,
                            RefreshTokenRecord(
                                **{**candidate.record.__dict__, "active": False}
                            ),
                        )
                return current
            self._tokens[new_token_id] = _StoredRefreshToken(
                self._hash(new_token),
                RefreshTokenRecord(
                    token_id=new_token_id,
                    user_id=user_id,
                    session_id=session_id,
                    expires_at=expires_at,
                    active=True,
                ),
            )
            return current

    async def revoke(self, token_id: UUID) -> None:
        async with self._lock:
            stored = self._tokens.get(token_id)
            if stored:
                self._tokens[token_id] = _StoredRefreshToken(
                    stored.token_hash,
                    RefreshTokenRecord(**{**stored.record.__dict__, "active": False}),
                )

    async def revoke_session(self, session_id: UUID) -> None:
        async with self._lock:
            for token_id, stored in self._tokens.items():
                if stored.record.session_id == session_id and stored.record.active:
                    self._tokens[token_id] = _StoredRefreshToken(
                        stored.token_hash,
                        RefreshTokenRecord(**{**stored.record.__dict__, "active": False}),
                    )

    async def revoke_user(self, user_id: int) -> None:
        async with self._lock:
            for token_id, stored in self._tokens.items():
                if stored.record.user_id == user_id and stored.record.active:
                    self._tokens[token_id] = _StoredRefreshToken(
                        stored.token_hash,
                        RefreshTokenRecord(**{**stored.record.__dict__, "active": False}),
                    )
