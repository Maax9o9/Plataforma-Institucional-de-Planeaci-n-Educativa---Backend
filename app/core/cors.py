"""Configuracion segura de CORS para la API."""

from __future__ import annotations

from urllib.parse import urlsplit

from .config import Settings

DEFAULT_DEVELOPMENT_ORIGINS = (
    "http://localhost:3000",
    "http://localhost:5173",
)


def _normalize_origin(origin: str) -> str:
    value = origin.strip().rstrip("/")
    if value == "*":
        raise RuntimeError(
            "CORS_ORIGINS no puede usar '*' cuando allow_credentials esta habilitado."
        )

    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise RuntimeError(
            f"Origen CORS invalido: {origin!r}. Usa una URL como https://frontend.example.com."
        )
    return value


def build_cors_options(settings: Settings) -> dict:
    if settings.cors_allow_all:
        if settings.environment == "production":
            raise RuntimeError("CORS_ALLOW_ALL no puede habilitarse en produccion.")
        return {
            "allow_origins": ["*"],
            "allow_credentials": False,
            "allow_methods": ["*"],
            "allow_headers": ["*"],
            "expose_headers": ["X-Request-ID"],
            "max_age": 600,
        }

    origins = settings.cors_origins
    if not origins:
        if settings.environment in {"development", "testing"}:
            origins = list(DEFAULT_DEVELOPMENT_ORIGINS)
        else:
            raise RuntimeError(
                "CORS_ORIGINS debe configurarse explicitamente en staging y produccion."
            )

    normalized_origins = list(dict.fromkeys(_normalize_origin(origin) for origin in origins))
    return {
        "allow_origins": normalized_origins,
        "allow_credentials": True,
        "allow_methods": ["GET", "POST", "PATCH"],
        "allow_headers": ["Accept", "Authorization", "Content-Type", "X-Request-ID"],
        "expose_headers": ["X-Request-ID"],
        "max_age": 600,
    }
