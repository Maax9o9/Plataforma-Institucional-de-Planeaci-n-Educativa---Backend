"""Contrato de tokens consumido por los casos de uso."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from ..entities import User


@dataclass(frozen=True)
class AccessTokenClaims:
    subject: int
    roles: tuple[str, ...]
    area_id: int | None
    token_id: UUID
    expires_at: datetime
    password_version: int = 0


@dataclass(frozen=True)
class RefreshTokenClaims:
    subject: int
    session_id: UUID
    token_id: UUID
    expires_at: datetime
    password_version: int = 0


@dataclass(frozen=True)
class IssuedRefreshToken:
    token: str
    token_id: UUID
    session_id: UUID
    expires_at: datetime


class TokenService(Protocol):
    def issue_access(self, user: User) -> str: ...

    def issue_refresh(self, user: User, session_id: UUID) -> IssuedRefreshToken: ...

    def decode_access(self, token: str) -> AccessTokenClaims: ...

    def decode_refresh(self, token: str) -> RefreshTokenClaims: ...
