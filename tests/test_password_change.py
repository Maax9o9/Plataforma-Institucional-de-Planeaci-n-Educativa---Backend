import os
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app
from app.modules.identity_access.application.dto import RegisterUserCommand
from app.modules.identity_access.application.use_cases.change_password import ChangeAdminPassword
from app.modules.identity_access.application.use_cases.create_user import CreateUser
from app.modules.identity_access.domain.value_objects import Role

ENDPOINT = "/api/v1/auth/cambiar-contrasena"


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL no configurada")
@pytest.mark.asyncio
async def test_postgres_password_change_rolls_back_on_audit_failure(monkeypatch):
    application = create_app(
        Settings(
            environment="testing",
            indicators_module_enabled=True,
            database_url=os.environ["TEST_DATABASE_URL"],
            secret_key="test-secret-key-with-more-than-32-characters",
            email_provider="console",
        )
    )
    try:
        user = await create_account(application, Role.ADMIN_SISTEMA)
        old_hash = user.password_hash
        async with AsyncClient(
            transport=ASGITransport(app=application), base_url="http://testserver"
        ) as client:
            login = await client.post(
                "/api/v1/auth/login",
                json={
                    "correo": user.email.value,
                    "contrasena": "initial-password-private",
                },
            )
            assert login.status_code == 200
            with monkeypatch.context() as patch:
                patch.setattr(
                    application.state.audit_repository,
                    "append",
                    AsyncMock(side_effect=RuntimeError),
                )
                use_case = ChangeAdminPassword(
                    application.state.user_repository,
                    application.state.password_hasher,
                    application.state.refresh_token_store,
                    application.state.event_bus,
                    application.state.unit_of_work,
                )
                with pytest.raises(RuntimeError):
                    await use_case.execute(
                        user.id, "initial-password-private", "new-password-private"
                    )
            current = await application.state.user_repository.get_by_id(user.id)
            assert current.password_hash == old_hash
            assert current.password_version == 0
            assert (await client.post("/api/v1/auth/refresh")).status_code == 200
    finally:
        await application.state.db_engine.dispose()


async def create_account(app, role):
    return await CreateUser(
        app.state.user_repository, app.state.password_hasher, app.state.event_bus
    ).execute(
        RegisterUserCommand(
            email=f"password-{uuid4().hex}@example.com",
            full_name="Cuenta de prueba",
            password="initial-password-private",
            roles={role},
            area_id=None,
        )
    )


@pytest.mark.asyncio
async def test_admin_private_password_revokes_all_sessions(backend_client):
    app, client = backend_client
    user = await create_account(app, Role.ADMIN_SISTEMA)

    async def login(password):
        return await client.post(
            "/api/v1/auth/login",
            json={
                "correo": user.email.value,
                "contrasena": password,
            },
        )

    first = await login("initial-password-private")
    assert first.status_code == 200, first.text
    headers = {"Authorization": f"Bearer {first.json()['access_token']}"}
    refresh_one = client.cookies.get(app.state.settings.refresh_cookie_name)
    second = await login("initial-password-private")
    other_headers = {"Authorization": f"Bearer {second.json()['access_token']}"}
    refresh_two = client.cookies.get(app.state.settings.refresh_cookie_name)
    payload = {
        "contrasena_actual": "initial-password-private",
        "contrasena_nueva": "new-password-only-owner",
        "confirmar_contrasena": "new-password-only-owner",
    }
    mismatch = await client.post(
        ENDPOINT,
        headers=headers,
        json={
            **payload,
            "confirmar_contrasena": "wrong-confirmation",
        },
    )
    assert mismatch.status_code == 422, mismatch.text
    assert "initial-password-private" not in mismatch.text
    assert "new-password-only-owner" not in mismatch.text
    other_target = await client.post(ENDPOINT, headers=headers, json={**payload, "user_id": 999})
    assert other_target.status_code == 422
    wrong = await client.post(
        ENDPOINT,
        headers=headers,
        json={
            **payload,
            "contrasena_actual": "wrong-current-password",
        },
    )
    assert wrong.status_code == 401, wrong.text
    same = await client.post(
        ENDPOINT,
        headers=headers,
        json={
            **payload,
            "contrasena_nueva": payload["contrasena_actual"],
            "confirmar_contrasena": payload["contrasena_actual"],
        },
    )
    assert same.status_code == 422, same.text
    changed = await client.post(ENDPOINT, headers=headers, json=payload)
    assert changed.status_code == 204, changed.text
    assert not changed.content
    assert "Max-Age=0" in changed.headers["set-cookie"]
    for session_headers in (headers, other_headers):
        assert (await client.get("/api/v1/auth/me", headers=session_headers)).status_code == 401
    for refresh in (refresh_one, refresh_two):
        response = await client.post(
            "/api/v1/auth/refresh",
            headers={
                "Cookie": f"{app.state.settings.refresh_cookie_name}={refresh}",
            },
        )
        assert response.status_code == 401, response.text
    assert (await login("initial-password-private")).status_code == 401
    new_login = await login("new-password-only-owner")
    assert new_login.status_code == 200, new_login.text
    current = await app.state.user_repository.get_by_id(user.id)
    assert current.password_version == 1
    assert app.state.password_hasher.verify("new-password-only-owner", current.password_hash)
    events = await app.state.audit_repository.list(aggregate_type="user", aggregate_id=user.id)
    changes = [e for e in events if e.action == "password_changed"]
    assert len(changes) == 1
    assert changes[0].data == {}


@pytest.mark.asyncio
async def test_password_change_requires_admin_and_current_password(client, app):
    payload = {
        "contrasena_actual": "initial-password-private",
        "contrasena_nueva": "new-private-password",
        "confirmar_contrasena": "new-private-password",
    }
    assert (await client.post(ENDPOINT, json=payload)).status_code == 401
    for role in (Role.PLANEACION, Role.PLANEACION_ADMIN):
        user = await create_account(app, role)
        login = await client.post(
            "/api/v1/auth/login",
            json={
                "correo": user.email.value,
                "contrasena": "initial-password-private",
            },
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        response = await client.post(ENDPOINT, headers=headers, json=payload)
        assert response.status_code == (204 if role is Role.PLANEACION_ADMIN else 403), (
            response.text
        )
