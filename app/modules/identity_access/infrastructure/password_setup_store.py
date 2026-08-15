"""Implementaciones en memoria y PostgreSQL del token de invitacion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .models import PasswordSetupTokenModel


@dataclass
class _PendingToken:
    user_id: int
    expires_at: datetime
    used: bool = False


class InMemoryPasswordSetupTokenStore:
    def __init__(self) -> None:
        self._tokens: dict[str, _PendingToken] = {}

    async def issue(self, *, user_id: int, token_hash: str, expires_at: datetime) -> UUID:
        token_id = uuid4()
        self._tokens[token_hash] = _PendingToken(user_id=user_id, expires_at=expires_at)
        return token_id

    async def consume(self, token_hash: str) -> int | None:
        item = self._tokens.get(token_hash)
        if item is None or item.used or item.expires_at <= datetime.now(UTC):
            return None
        item.used = True
        return item.user_id

    async def is_valid(self, token_hash: str) -> bool:
        item = self._tokens.get(token_hash)
        return item is not None and not item.used and item.expires_at > datetime.now(UTC)


class SqlAlchemyPasswordSetupTokenStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def issue(self, *, user_id: int, token_hash: str, expires_at: datetime) -> UUID:
        token_id = uuid4()
        async with self.session_factory() as session:
            session.add(
                PasswordSetupTokenModel(
                    id=token_id,
                    usuario_id=user_id,
                    hash_token=token_hash,
                    expira_en=expires_at,
                    creado_en=datetime.now(UTC),
                )
            )
            await session.commit()
        return token_id

    async def consume(self, token_hash: str) -> int | None:
        async with self.session_factory() as session:
            model = (
                await session.execute(
                    select(PasswordSetupTokenModel).where(
                        PasswordSetupTokenModel.hash_token == token_hash,
                        PasswordSetupTokenModel.usado_en.is_(None),
                        PasswordSetupTokenModel.expira_en > datetime.now(UTC),
                    ).with_for_update()
                )
            ).scalar_one_or_none()
            if model is None:
                return None
            model.usado_en = datetime.now(UTC)
            await session.commit()
            return model.usuario_id

    async def is_valid(self, token_hash: str) -> bool:
        async with self.session_factory() as session:
            model = (
                await session.execute(
                    select(PasswordSetupTokenModel).where(
                        PasswordSetupTokenModel.hash_token == token_hash,
                        PasswordSetupTokenModel.usado_en.is_(None),
                        PasswordSetupTokenModel.expira_en > datetime.now(UTC),
                    )
                )
            ).scalar_one_or_none()
            return model is not None
