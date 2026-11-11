"""Blacklist temporal en memoria para access tokens."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select

from app.shared.infrastructure.db.unit_of_work import commit_or_flush, session_scope

from .models import RevokedAccessTokenModel


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


class SqlAlchemyRevokedTokenStore:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    async def revoke(self, token_id: UUID, expires_at: datetime) -> None:
        if expires_at <= datetime.now(UTC):
            return
        async with session_scope(self.session_factory) as session:
            model = await session.get(RevokedAccessTokenModel, token_id)
            if model is None:
                session.add(
                    RevokedAccessTokenModel(
                        jti=token_id,
                        expira_en=expires_at,
                        revocado_en=datetime.now(UTC),
                    )
                )
            else:
                model.expira_en = expires_at
                model.revocado_en = datetime.now(UTC)
            await commit_or_flush(session)

    async def is_revoked(self, token_id: UUID) -> bool:
        now = datetime.now(UTC)
        async with session_scope(self.session_factory) as session:
            expires_at = await session.scalar(
                select(RevokedAccessTokenModel.expira_en).where(
                    RevokedAccessTokenModel.jti == token_id
                )
            )
            if expires_at is None:
                return False
            if expires_at <= now:
                await session.execute(
                    delete(RevokedAccessTokenModel).where(
                        RevokedAccessTokenModel.jti == token_id
                    )
                )
                await commit_or_flush(session)
                return False
            return True
