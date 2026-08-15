"""Repositorio temporal en memoria; implementa los puertos de identidad."""

from __future__ import annotations

import asyncio
from itertools import count

from app.shared.domain.exceptions import ConflictError

from ..domain.entities import User


class InMemoryUserRepository:
    def __init__(self) -> None:
        self._users: dict[int, User] = {}
        self._email_index: dict[str, int] = {}
        self._next_id = count(1)
        self._lock = asyncio.Lock()

    async def get_by_id(self, user_id: int) -> User | None:
        return self._users.get(user_id)

    async def get_by_email(self, email: str) -> User | None:
        user_id = self._email_index.get(email.strip().lower())
        return self._users.get(user_id) if user_id else None

    async def list(self, *, active_only: bool = False) -> list[User]:
        users = list(self._users.values())
        return [user for user in users if user.is_active] if active_only else users

    async def add(self, user: User) -> None:
        async with self._lock:
            if user.email.value in self._email_index:
                raise ConflictError("Ya existe un usuario con ese correo electronico.")
            if user.id == 0:
                user.id = next(self._next_id)
            self._users[user.id] = user
            self._email_index[user.email.value] = user.id

    async def update(self, user: User) -> None:
        async with self._lock:
            if user.id not in self._users:
                return
            self._users[user.id] = user

    async def all(self) -> list[User]:
        return list(self._users.values())
