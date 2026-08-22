"""Unidad de trabajo SQLAlchemy compartida por una operacion de aplicacion."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from contextvars import ContextVar

from sqlalchemy.ext.asyncio import AsyncSession

_ambient_session: ContextVar[AsyncSession | None] = ContextVar(
    "ambient_database_session", default=None
)
_after_commit: ContextVar[list[Callable[[], Awaitable[None]]] | None] = ContextVar(
    "after_commit_callbacks", default=None
)


@asynccontextmanager
async def session_scope(session_factory):
    """Reutiliza la sesion de la unidad de trabajo o crea una sesion autonoma."""

    session = _ambient_session.get()
    if session is not None:
        yield session
        return
    async with session_factory() as owned_session:
        yield owned_session


async def commit_or_flush(session: AsyncSession) -> None:
    if _ambient_session.get() is session:
        await session.flush()
    else:
        await session.commit()


async def run_after_commit(callback: Callable[[], Awaitable[None]]) -> None:
    callbacks = _after_commit.get()
    if callbacks is None:
        await callback()
    else:
        callbacks.append(callback)


class SqlAlchemyUnitOfWork:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory
        self.session = None
        self._token = None
        self._callbacks_token = None

    async def __aenter__(self):
        if _ambient_session.get() is not None:
            return self
        self.session = self.session_factory()
        await self.session.begin()
        self._token = _ambient_session.set(self.session)
        self._callbacks_token = _after_commit.set([])
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        if self.session is None:
            return False
        callbacks = _after_commit.get() or []
        committed = False
        try:
            if exc_type is None:
                await self.session.commit()
                committed = True
            else:
                await self.session.rollback()
        finally:
            _ambient_session.reset(self._token)
            _after_commit.reset(self._callbacks_token)
            await self.session.close()
            self.session = None
            self._token = None
            self._callbacks_token = None
        if committed:
            for callback in callbacks:
                await callback()
        return False


class NoOpUnitOfWork:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class SqlAlchemyUnitOfWorkFactory:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    def __call__(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(self.session_factory)


class NoOpUnitOfWorkFactory:
    def __call__(self) -> NoOpUnitOfWork:
        return NoOpUnitOfWork()
