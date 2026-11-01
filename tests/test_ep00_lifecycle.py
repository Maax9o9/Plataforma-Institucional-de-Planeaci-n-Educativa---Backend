from __future__ import annotations

import re
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
        json={
            "correo": "admin-lifecycle@upchiapas.edu.mx",
            "contrasena": "password-seguro",
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
    setup_url = re.search(r"https?://\S+\?token=\S+", email_sender.messages[0][2]).group()
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
        json={
            "correo": "consulta-lifecycle@upchiapas.edu.mx",
            "contrasena": "password-consulta",
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
        json={
            "correo": "consulta-lifecycle@upchiapas.edu.mx",
            "contrasena": "password-consulta",
        },
    )
    assert allowed.status_code == 200


async def _cuenta(app, client, correo: str, rol: Role) -> dict[str, str]:
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
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _invitar(client, headers, correo: str, roles: list[str]):
    return await client.post(
        "/api/v1/usuarios",
        headers=headers,
        json={"correo": correo, "nombre": "Invitación", "roles": roles},
    )


@pytest.mark.asyncio
async def test_el_alta_no_revela_si_un_correo_tiene_cuenta_a_quien_no_puede_preguntarlo(
    app, client
):
    admin = await _cuenta(app, client, "admin-fuga@upchiapas.edu.mx", Role.ADMIN_SISTEMA)
    planeacion = await _cuenta(app, client, "planeacion-fuga@upchiapas.edu.mx", Role.PLANEACION)
    ya_tiene_cuenta = "ya-tiene-cuenta@upchiapas.edu.mx"
    nadie_lo_usa = "nadie-lo-usa@upchiapas.edu.mx"
    creado = await _invitar(client, admin, ya_tiene_cuenta, ["consulta"])
    assert creado.status_code == 201, creado.text

    existente = await _invitar(client, planeacion, ya_tiene_cuenta, ["admin_sistema"])
    inventado = await _invitar(client, planeacion, nadie_lo_usa, ["admin_sistema"])

    assert (existente.status_code, existente.json()["code"]) == (403, "FORBIDDEN"), existente.text
    assert (inventado.status_code, inventado.json()["code"]) == (403, "FORBIDDEN"), inventado.text
    assert existente.json() == inventado.json() | {"request_id": existente.json()["request_id"]}


@pytest.mark.asyncio
async def test_quien_si_puede_dar_de_alta_sigue_recibiendo_el_409_del_correo_repetido(app, client):
    admin = await _cuenta(app, client, "admin-repetido@upchiapas.edu.mx", Role.ADMIN_SISTEMA)
    correo = "repetido@upchiapas.edu.mx"
    creado = await _invitar(client, admin, correo, ["consulta"])
    assert creado.status_code == 201, creado.text

    otra_vez = await _invitar(client, admin, correo, ["consulta"])

    assert otra_vez.status_code == 409, otra_vez.text
    assert otra_vez.json()["code"] == "CONFLICT"
