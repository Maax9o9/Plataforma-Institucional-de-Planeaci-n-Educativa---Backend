from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture(params=["memory", "postgresql"])
async def backend_client(request, tmp_path):
    import os

    database_url = None
    if request.param == "postgresql":
        database_url = os.getenv("TEST_DATABASE_URL")
        if not database_url:
            pytest.skip("TEST_DATABASE_URL no configurada")
    application = create_app(
        Settings(
            environment="testing",
            database_url=database_url,
            email_provider="console",
            secret_key="test-secret-key-with-more-than-32-characters",
            upload_directory=str(tmp_path),
        )
    )
    try:
        await application.state.poa_form_repository.ensure_catalogs()
        async with AsyncClient(
            transport=ASGITransport(app=application), base_url="http://testserver"
        ) as client:
            yield application, client
    finally:
        await application.state.notification_service.close()
        if application.state.db_engine is not None:
            await application.state.db_engine.dispose()


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
