from __future__ import annotations

import pytest

from app.modules.identity_access.application.dto import RegisterUserCommand
from app.modules.identity_access.application.use_cases.create_user import CreateUser
from app.modules.identity_access.domain.value_objects import Role


@pytest.mark.asyncio
async def test_invitation_assigns_exact_directory_area_and_roles(client, app):
    await CreateUser(
        repository=app.state.user_repository,
        password_hasher=app.state.password_hasher,
        event_bus=app.state.event_bus,
    ).execute(
        RegisterUserCommand(
            email="admin-directorio@upchiapas.edu.mx",
            full_name="Administrador",
            password="password-seguro",
            roles={Role.ADMIN_SISTEMA},
            area_id=None,
        )
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "correo": "admin-directorio@upchiapas.edu.mx",
            "contrasena": "password-seguro",
        },
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    invited = await client.post(
        "/api/v1/usuarios",
        json={
            "correo": "planeacion@upchiapas.edu.mx",
            "nombre": "Cuenta de Planeación",
            "roles": ["consulta"],
        },
        headers=headers,
    )
    assert invited.status_code == 201, invited.text
    body = invited.json()
    assert body["area_nombre"] == "Dirección de Planeación Educativa"
    assert set(body["roles"]) == {
        "planeacion_admin",
        "capturista_poa",
        "revisor_poa",
    }
    assert body["requiere_configurar_contrasena"] is True
