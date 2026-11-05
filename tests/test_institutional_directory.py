from __future__ import annotations

import pytest

from app.modules.identity_access.application.dto import RegisterUserCommand
from app.modules.identity_access.application.use_cases.create_user import CreateUser
from app.modules.identity_access.domain.value_objects import Role
from app.shared.application.ports.email_sender import EmailSendError


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


async def _admin_headers(client, app) -> dict[str, str]:
    await CreateUser(
        repository=app.state.user_repository,
        password_hasher=app.state.password_hasher,
        event_bus=app.state.event_bus,
    ).execute(
        RegisterUserCommand(
            email="admin-correo@upchiapas.edu.mx",
            full_name="Administrador",
            password="password-seguro",
            roles={Role.ADMIN_SISTEMA},
            area_id=None,
        )
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "correo": "admin-correo@upchiapas.edu.mx",
            "contrasena": "password-seguro",
        },
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


class _CorreoCaido:
    """Un servicio de correo que no responde, como el de una red sin salida."""

    def __init__(self) -> None:
        self.intentos = 0

    async def send(self, recipient: str, subject: str, html: str, text: str) -> None:
        self.intentos += 1
        raise EmailSendError(f"No se pudo enviar correo a {recipient}.")


@pytest.mark.asyncio
async def test_invitation_survives_a_failing_email(client, app):
    headers = await _admin_headers(client, app)
    correo_caido = _CorreoCaido()
    app.state.email_sender = correo_caido

    invited = await client.post(
        "/api/v1/usuarios",
        json={
            "correo": "serviciosacademicos@upchiapas.edu.mx",
            "nombre": "Cuenta de Servicios Académicos",
            "roles": ["consulta"],
        },
        headers=headers,
    )

    assert correo_caido.intentos == 1
    assert invited.status_code == 201, invited.text
    assert invited.json()["correo_enviado"] is False
    assert invited.json()["requiere_configurar_contrasena"] is True


@pytest.mark.asyncio
async def test_invitation_with_a_working_email_says_so(client, app):
    headers = await _admin_headers(client, app)

    invited = await client.post(
        "/api/v1/usuarios",
        json={
            "correo": "vinculacion@upchiapas.edu.mx",
            "nombre": "Cuenta de Vinculación",
            "roles": ["consulta"],
        },
        headers=headers,
    )

    assert invited.status_code == 201, invited.text
    assert invited.json()["correo_enviado"] is True


@pytest.mark.asyncio
async def test_the_account_of_a_failed_email_can_be_consulted_and_set_its_password(client, app):
    headers = await _admin_headers(client, app)
    app.state.email_sender = _CorreoCaido()

    await client.post(
        "/api/v1/usuarios",
        json={
            "correo": "posgrado@upchiapas.edu.mx",
            "nombre": "Cuenta de Innovación Educativa",
            "roles": ["consulta"],
        },
        headers=headers,
    )

    listado = await client.get(
        "/api/v1/usuarios?q=posgrado@upchiapas.edu.mx", headers=headers
    )

    assert listado.status_code == 200, listado.text
    assert listado.json()["total"] == 1
    assert "correo_enviado" not in listado.json()["items"][0]
