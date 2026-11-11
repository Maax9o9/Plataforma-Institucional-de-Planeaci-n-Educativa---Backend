"""Contratos de lectura y escritura de usuarios."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from ..entities import User


class UserReader(Protocol):
    async def get_by_id(self, user_id: int) -> User | None: ...

    async def get_by_email(self, email: str) -> User | None: ...

    async def list(self, *, active_only: bool = False) -> list[User]: ...


class UserWriter(Protocol):
    async def add(self, user: User) -> None: ...

    async def update(self, user: User) -> None: ...

    async def record_access(self, user_id: int, occurred_at: datetime) -> None: ...


class UserRepository(UserReader, UserWriter, Protocol):
    pass
