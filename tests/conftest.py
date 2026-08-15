from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def app():
    return create_app(
        Settings(
            environment="testing",
            secret_key="test-secret-key-with-more-than-32-characters",
            database_url=None,
            email_provider="console",
            bootstrap_admin_email=None,
            bootstrap_admin_password=None,
        )
    )


@pytest.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as async_client:
        yield async_client
