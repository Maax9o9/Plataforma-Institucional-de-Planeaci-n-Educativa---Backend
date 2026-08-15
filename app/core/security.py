"""Primitivas tecnicas de contrasenas, JWT y autorizacion RBAC."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import jwt
from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash

from app.shared.domain.exceptions import AuthenticationError, ForbiddenError

password_hash = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def hash_password(value: str) -> str:
    return password_hash.hash(value)


def verify_password(value: str, hashed_value: str) -> bool:
    return password_hash.verify(value, hashed_value)


def encode_jwt(payload: dict[str, Any], expires_at: datetime, settings) -> str:
    claims = {**payload, "exp": expires_at}
    return jwt.encode(
        claims,
        settings.secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def decode_jwt(token: str, settings) -> dict[str, Any]:
    try:
        return jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "iat", "sub", "jti", "type"]},
        )
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("El token no es valido o ya expiro.") from exc


async def get_access_claims(request: Request, token: str = Depends(oauth2_scheme)):
    claims = request.app.state.token_service.decode_access(token)
    if await request.app.state.revoked_token_store.is_revoked(claims.token_id):
        raise AuthenticationError("El token fue revocado.")
    return claims


async def get_current_user(request: Request, claims=Depends(get_access_claims)):
    user = await request.app.state.user_repository.get_by_id(claims.subject)
    if user is None or not user.is_active:
        raise AuthenticationError("El usuario no esta disponible.")
    return user


def require_roles(*roles: str):
    """Crea una dependencia de FastAPI para autorizacion RBAC reutilizable."""

    async def dependency(current_user=Depends(get_current_user)):
        current_roles = {
            role.value if hasattr(role, "value") else str(role) for role in current_user.roles
        }
        if not current_roles.intersection(roles):
            raise ForbiddenError()
        return current_user

    return dependency
