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


async def _invitar(client, headers, correo: str, nombre: str) -> dict:
    invitado = await client.post(
        "/api/v1/usuarios",
        json={"correo": correo, "nombre": nombre, "roles": ["consulta"]},
        headers=headers,
    )
    assert invitado.status_code == 201, invitado.text
    return invitado.json()


@pytest.mark.asyncio
async def test_resending_the_invitation_sends_the_email_again(client, app):
    headers = await _admin_headers(client, app)
    correo_caido = _CorreoCaido()
    app.state.email_sender = correo_caido
    invitado = await _invitar(client, headers, "reenvio1@upchiapas.edu.mx", "Cuenta uno")
    assert invitado["correo_enviado"] is False

    app.state.email_sender = _CorreoQueSiSale()
    reenviado = await client.post(
        f"/api/v1/usuarios/{invitado['id']}/reenviar-invitacion", headers=headers
    )

    assert reenviado.status_code == 200, reenviado.text
    assert reenviado.json()["correo_enviado"] is True
    assert reenviado.json()["id"] == invitado["id"]


@pytest.mark.asyncio
async def test_a_resent_invitation_that_fails_says_so_without_losing_the_account(client, app):
    headers = await _admin_headers(client, app)
    invitado = await _invitar(client, headers, "reenvio2@upchiapas.edu.mx", "Cuenta dos")
    correo_caido = _CorreoCaido()
    app.state.email_sender = correo_caido

    reenviado = await client.post(
        f"/api/v1/usuarios/{invitado['id']}/reenviar-invitacion", headers=headers
    )

    assert reenviado.status_code == 200, reenviado.text
    assert reenviado.json()["correo_enviado"] is False
    assert correo_caido.intentos == 1


@pytest.mark.asyncio
async def test_the_resent_link_lets_the_person_set_the_password(client, app):
    headers = await _admin_headers(client, app)
    enlaces = _CorreoQueSiSale()
    app.state.email_sender = enlaces
    invitado = await _invitar(client, headers, "reenvio3@upchiapas.edu.mx", "Cuenta tres")

    await client.post(f"/api/v1/usuarios/{invitado['id']}/reenviar-invitacion", headers=headers)

    assert len(enlaces.enviados) == 2
    ultimo = _token_del_enlace(enlaces.enviados[-1])
    valido = await client.post("/api/v1/auth/password-setup/validar", json={"token": ultimo})
    assert valido.status_code == 200, valido.text
    assert valido.json()["valido"] is True


@pytest.mark.asyncio
async def test_resending_to_someone_who_already_has_a_password_is_refused(client, app):
    headers = await _admin_headers(client, app)
    enlaces = _CorreoQueSiSale()
    app.state.email_sender = enlaces
    invitado = await _invitar(client, headers, "reenvio4@upchiapas.edu.mx", "Cuenta cuatro")
    establecida = await client.post(
        "/api/v1/auth/password-setup",
        json={"token": _token_del_enlace(enlaces.enviados[-1]), "contrasena": "password-seguro"},
    )
    assert establecida.status_code in (200, 204), establecida.text

    reenviado = await client.post(
        f"/api/v1/usuarios/{invitado['id']}/reenviar-invitacion", headers=headers
    )

    assert reenviado.status_code == 409, reenviado.text
    assert "ya configuró su contraseña" in reenviado.json()["message"]


@pytest.mark.asyncio
async def test_resending_to_a_user_that_does_not_exist_says_so(client, app):
    headers = await _admin_headers(client, app)

    reenviado = await client.post("/api/v1/usuarios/999999/reenviar-invitacion", headers=headers)

    assert reenviado.status_code == 404, reenviado.text


@pytest.mark.asyncio
async def test_only_planning_or_admin_can_resend_an_invitation(client, app):
    headers = await _admin_headers(client, app)
    invitado = await _invitar(client, headers, "reenvio5@upchiapas.edu.mx", "Cuenta cinco")
    ajenas = await _headers_de_rol(client, app, Role.CAPTURISTA_POA, "ajeno-reenvio")

    reenviado = await client.post(
        f"/api/v1/usuarios/{invitado['id']}/reenviar-invitacion", headers=ajenas
    )

    assert reenviado.status_code == 403, reenviado.text


class _CorreoQueSiSale:
    def __init__(self) -> None:
        self.enviados: list[str] = []

    async def send(self, recipient: str, subject: str, html: str, text: str) -> None:
        self.enviados.append(text)


def _token_del_enlace(cuerpo: str) -> str:
    import re

    encontrado = re.search(r"establecer-contrasena\?token=([A-Za-z0-9_\-]+)", cuerpo)
    assert encontrado is not None, cuerpo
    return encontrado.group(1)


async def _headers_de_rol(client, app, rol: Role, prefijo: str) -> dict[str, str]:
    correo = f"{prefijo}@upchiapas.edu.mx"
    await CreateUser(
        repository=app.state.user_repository,
        password_hasher=app.state.password_hasher,
        event_bus=app.state.event_bus,
    ).execute(
        RegisterUserCommand(
            email=correo,
            full_name=f"Cuenta {rol.value}",
            password="password-seguro",
            roles={rol},
            area_id=None,
        )
    )
    login = await client.post(
        "/api/v1/auth/login", json={"correo": correo, "contrasena": "password-seguro"}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_planning_cannot_resend_the_invitation_of_an_administrator(client, app):
    de_planeacion = await _headers_de_rol(client, app, Role.PLANEACION, "planeacion-reenvio")
    administrador = await CreateUser(
        repository=app.state.user_repository,
        password_hasher=app.state.password_hasher,
        event_bus=app.state.event_bus,
    ).execute(
        RegisterUserCommand(
            email="otro-admin-reenvio@upchiapas.edu.mx",
            full_name="Otra administración",
            password="password-seguro",
            roles={Role.ADMIN_SISTEMA},
            area_id=None,
        )
    )

    reenviado = await client.post(
        f"/api/v1/usuarios/{administrador.id}/reenviar-invitacion", headers=de_planeacion
    )

    assert reenviado.status_code == 403, reenviado.text
