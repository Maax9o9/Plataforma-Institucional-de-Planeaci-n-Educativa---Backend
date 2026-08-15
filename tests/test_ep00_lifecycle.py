from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from app.modules.identity_access.application.dto import RegisterUserCommand
from app.modules.identity_access.application.use_cases.create_user import CreateUser
from app.modules.identity_access.domain.value_objects import Role


@pytest.mark.asyncio
async def test_user_creation_edit_deactivation_and_reactivation(client, app):
    class CapturingEmailSender:
        def __init__(self):
            self.messages = []

        async def send(self, recipient, subject, html_body, text_body=None):
            self.messages.append((recipient, subject, text_body or html_body))

    email_sender = CapturingEmailSender()
    app.state.email_sender = email_sender
    await CreateUser(
        repository=app.state.user_repository,
        password_hasher=app.state.password_hasher,
        event_bus=app.state.event_bus,
    ).execute(
        RegisterUserCommand(
            email="admin-lifecycle@upchiapas.edu.mx",
            full_name="Administrador",
            password="password-seguro",
            roles={Role.ADMIN_SISTEMA},
            area_id=None,
        )
    )
    login = await client.post(
        "/api/v1/auth/login",
        data={
            "username": "admin-lifecycle@upchiapas.edu.mx",
            "password": "password-seguro",
        },
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    created = await client.post(
        "/api/v1/usuarios",
        json={
            "correo": "consulta-lifecycle@upchiapas.edu.mx",
            "nombre": "Usuario Consulta",
            "contrasena": "password-consulta",
            "roles": ["consulta"],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]
    setup_url = email_sender.messages[0][2].split(": ", 1)[1]
    setup_token = parse_qs(urlparse(setup_url).query)["token"][0]
    configured = await client.post(
        "/api/v1/auth/password-setup",
        json={"token": setup_token, "contrasena": "password-consulta"},
    )
    assert configured.status_code == 204
    updated = await client.patch(
        f"/api/v1/usuarios/{user_id}",
        json={"nombre": "Usuario Consulta Editado"},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["nombre"] == "Usuario Consulta Editado"
    deactivated = await client.post(
        f"/api/v1/usuarios/{user_id}/desactivar",
        headers=headers,
    )
    assert deactivated.status_code == 200
    blocked = await client.post(
        "/api/v1/auth/login",
        data={
            "username": "consulta-lifecycle@upchiapas.edu.mx",
            "password": "password-consulta",
        },
    )
    assert blocked.status_code == 401
    reactivated = await client.post(
        f"/api/v1/usuarios/{user_id}/reactivar",
        headers=headers,
    )
    assert reactivated.status_code == 200
    allowed = await client.post(
        "/api/v1/auth/login",
        data={
            "username": "consulta-lifecycle@upchiapas.edu.mx",
            "password": "password-consulta",
        },
    )
    assert allowed.status_code == 200
