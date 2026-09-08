"""Adaptadores de Argon2 y JWT para los puertos de identidad."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.core.config import Settings
from app.core.security import decode_jwt, encode_jwt, hash_password, verify_password
from app.shared.domain.exceptions import AuthenticationError

from ..domain.entities import User
from ..domain.ports.token_service import (
    AccessTokenClaims,
    IssuedRefreshToken,
    RefreshTokenClaims,
)


class Argon2PasswordHasher:
    def hash(self, value: str) -> str:
        return hash_password(value)

    def verify(self, value: str, hashed_value: str) -> bool:
        return verify_password(value, hashed_value)


class JwtTokenService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def issue_access(self, user: User) -> str:
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=self.settings.access_token_expire_minutes)
        return encode_jwt(
            {
                "sub": str(user.id),
                "roles": [role.value for role in user.roles],
                "area_id": user.area_id,
                "iat": now,
                "jti": str(uuid4()),
                "type": "access",
                "pv": user.password_version,
            },
            expires_at,
            self.settings,
        )

    def issue_refresh(self, user: User, session_id: UUID) -> IssuedRefreshToken:
        now = datetime.now(UTC)
        expires_at = now + timedelta(days=self.settings.refresh_token_expire_days)
        token_id = uuid4()
        token = encode_jwt(
            {
                "sub": str(user.id),
                "session_id": str(session_id),
                "iat": now,
                "jti": str(token_id),
                "type": "refresh",
                "pv": user.password_version,
            },
            expires_at,
            self.settings,
        )
        return IssuedRefreshToken(
            token=token,
            token_id=token_id,
            session_id=session_id,
            expires_at=expires_at,
        )

    def decode_access(self, token: str) -> AccessTokenClaims:
        payload = decode_jwt(token, self.settings)
        if payload.get("type") != "access":
            raise AuthenticationError("El token no es un access token.")
        try:
            return AccessTokenClaims(
                subject=int(payload["sub"]),
                roles=tuple(str(role) for role in payload.get("roles", [])),
                area_id=int(payload["area_id"]) if payload.get("area_id") else None,
                token_id=UUID(str(payload["jti"])),
                expires_at=datetime.fromtimestamp(float(payload["exp"]), tz=UTC),
                password_version=int(payload.get("pv", 0)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AuthenticationError("El contenido del access token no es valido.") from exc

    def decode_refresh(self, token: str) -> RefreshTokenClaims:
        payload = decode_jwt(token, self.settings)
        if payload.get("type") != "refresh":
            raise AuthenticationError("El token no es un refresh token.")
        try:
            return RefreshTokenClaims(
                subject=int(payload["sub"]),
                session_id=UUID(str(payload["session_id"])),
                token_id=UUID(str(payload["jti"])),
                expires_at=datetime.fromtimestamp(float(payload["exp"]), tz=UTC),
                password_version=int(payload.get("pv", 0)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AuthenticationError("El contenido del refresh token no es valido.") from exc
