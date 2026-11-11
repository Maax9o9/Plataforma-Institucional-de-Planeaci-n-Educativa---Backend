"""Politica HTTP para la cookie del refresh token."""

from fastapi import Request, Response

from app.core.config import Settings
from app.shared.domain.exceptions import AuthenticationError


def _cookie_path(settings: Settings) -> str:
    return f"{settings.api_v1_prefix.rstrip('/')}/auth"


def read_refresh_cookie(
    request: Request,
    settings: Settings,
    *,
    required: bool = True,
) -> str | None:
    token = request.cookies.get(settings.refresh_cookie_name)
    if not token and required:
        raise AuthenticationError("La cookie de sesion no existe.")
    return token


def set_refresh_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=token,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        path=_cookie_path(settings),
        secure=settings.refresh_cookie_secure,
        httponly=True,
        samesite=settings.refresh_cookie_samesite,
    )


def clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=_cookie_path(settings),
        secure=settings.refresh_cookie_secure,
        httponly=True,
        samesite=settings.refresh_cookie_samesite,
    )
