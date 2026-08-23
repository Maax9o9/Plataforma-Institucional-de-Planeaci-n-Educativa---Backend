"""DTOs internos de los casos de uso de identidad."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from ..domain.value_objects import Role


@dataclass(frozen=True)
class RegisterUserCommand:
    email: str
    full_name: str
    password: str
    roles: set[Role]
    area_id: int | None
    actor_id: int | None = None


@dataclass(frozen=True)
class UpdateUserCommand:
    user_id: int
    email: str | None
    full_name: str | None
    roles: set[Role] | None
    area_id: int | None
    notify_email: bool | None
    expected_version: int | None
    actor_id: int


@dataclass(frozen=True)
class ChangeUserStatusCommand:
    user_id: int
    actor_id: int


@dataclass(frozen=True)
class AuthTokens:
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int


@dataclass(frozen=True)
class RefreshCommand:
    refresh_token: str


@dataclass(frozen=True)
class LogoutCommand:
    access_subject: int
    access_token_id: UUID
    access_expires_at: datetime
    refresh_token: str | None
