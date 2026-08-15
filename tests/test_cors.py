from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app


def make_settings(*, environment: str = "testing", origins: list[str] | None = None) -> Settings:
    return Settings(
        environment=environment,
        secret_key="test-secret-key-with-more-than-32-characters",
        database_url=None,
        email_provider="console",
        cors_origins=origins if origins is not None else ["http://localhost:5173"],
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
