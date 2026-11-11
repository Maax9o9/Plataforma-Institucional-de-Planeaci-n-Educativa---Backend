"""Factory de sesiones opcional mientras PostgreSQL no esta configurado."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings


def create_engine(settings: Settings):
    if not settings.database_url:
        return None

    database_url = settings.database_url
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return create_async_engine(
        database_url,
        echo=settings.database_echo,
        pool_pre_ping=True,
    )


def create_session_factory(settings: Settings):
    _, session_factory = create_database(settings)
    return session_factory


def create_database(
    settings: Settings,
) -> tuple[AsyncEngine | None, async_sessionmaker[AsyncSession] | None]:
    engine = create_engine(settings)
    if engine is None:
        return None, None
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Entrega una sesion de la aplicacion configurada en el composition root."""
    session_factory = request.app.state.db_session_factory
    if session_factory is None:
        raise RuntimeError("DATABASE_URL no esta configurada; la persistencia es en memoria.")

    async with session_factory() as session:
        yield session
