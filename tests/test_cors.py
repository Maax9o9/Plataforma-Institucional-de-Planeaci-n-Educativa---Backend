from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.responses import Response

from app.core.config import Settings
from app.main import create_app
from app.modules.identity_access.api.cookies import set_refresh_cookie


def make_settings(
    *,
    environment: str = "testing",
    origins: list[str] | None = None,
    allow_all: bool = False,
) -> Settings:
    return Settings(
        environment=environment,
        secret_key="test-secret-key-with-more-than-32-characters",
        database_url=None,
        email_provider="console",
        cors_allow_all=allow_all,
        cors_origins=origins if origins is not None else ["http://localhost:5173"],
        refresh_cookie_secure=environment == "production",
    )


@pytest.mark.asyncio
async def test_cors_preflight_allows_configured_origin():
    app = create_app(make_settings())
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.options(
            "/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization, Content-Type",
            },
        )
        health = await client.get(
            "/health",
            headers={"Origin": "http://localhost:5173"},
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "POST" in response.headers["access-control-allow-methods"]
    assert health.status_code == 200
    assert health.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "X-Request-ID" in health.headers["access-control-expose-headers"]


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["PUT", "DELETE"])
async def test_cors_preflight_allows_all_api_write_methods(method):
    app = create_app(make_settings())
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.options(
            "/api/v1/evidencias/1/version",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": "Authorization, Content-Type",
            },
        )
    assert response.status_code == 200
    assert method in response.headers["access-control-allow-methods"]


@pytest.mark.asyncio
async def test_cors_preflight_rejects_unconfigured_origin():
    app = create_app(make_settings())
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.options(
            "/health",
            headers={
                "Origin": "https://malicious.example",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_production_requires_explicit_cors_origins():
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        create_app(make_settings(environment="production", origins=[]))


def test_cors_rejects_wildcard_with_credentials():
    with pytest.raises(RuntimeError, match=r"\*"):
        create_app(make_settings(origins=["*"]))


def test_cors_allow_all_is_available_only_for_non_production():
    create_app(make_settings(allow_all=True))

    with pytest.raises(RuntimeError, match="CORS_ALLOW_ALL"):
        create_app(make_settings(environment="production", allow_all=True))


def test_production_requires_secure_refresh_cookie():
    settings = make_settings(environment="production")
    settings.refresh_cookie_secure = False
    with pytest.raises(RuntimeError, match="REFRESH_COOKIE_SECURE"):
        create_app(settings)


def test_samesite_none_requires_secure_cookie():
    settings = make_settings()
    settings.refresh_cookie_samesite = "none"
    with pytest.raises(RuntimeError, match="SameSite=None"):
        create_app(settings)


def test_cross_site_refresh_cookie_is_httponly_secure_and_samesite_none():
    settings = make_settings()
    settings.refresh_cookie_secure = True
    settings.refresh_cookie_samesite = "none"
    response = Response()

    set_refresh_cookie(response, "token-de-prueba", settings)

    header = response.headers["set-cookie"]
    assert "HttpOnly" in header
    assert "Secure" in header
    assert "SameSite=none" in header
