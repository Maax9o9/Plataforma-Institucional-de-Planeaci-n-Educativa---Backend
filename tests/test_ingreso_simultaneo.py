"""Entrar al sistema dos veces a la vez con la misma cuenta.

Pasa de verdad: la misma persona con la computadora y el teléfono, una cuenta
de área que dos personas comparten, o la pantalla que se recarga mientras la
sesión caduca. Hasta aquí el segundo ingreso rebotaba con un 409 porque el
inicio de sesión escribía al usuario completo con control de versión, y dos
escrituras simultáneas del mismo renglón no pueden ganar las dos.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from app.modules.identity_access.application.dto import RegisterUserCommand
from app.modules.identity_access.application.use_cases.create_user import CreateUser
from app.modules.identity_access.domain.value_objects import Role

CONTRASENA = "password-seguro"


async def _cuenta(app) -> str:
    correo = f"dos-sesiones-{uuid4().hex[:8]}@upchiapas.edu.mx"
    await CreateUser(
        app.state.user_repository, app.state.password_hasher, app.state.event_bus
    ).execute(
        RegisterUserCommand(
            email=correo,
            full_name="Quien entra dos veces",
            password=CONTRASENA,
            roles={Role.PLANEACION},
            area_id=None,
        )
    )
    return correo


async def _entrar(client, correo: str):
    return await client.post(
        "/api/v1/auth/login", json={"correo": correo, "contrasena": CONTRASENA}
    )


async def test_varios_ingresos_a_la_vez_de_la_misma_cuenta_entran_todos(backend_client):
    app, client = backend_client
    correo = await _cuenta(app)

    respuestas = await asyncio.gather(*[_entrar(client, correo) for _ in range(6)])

    assert [una.status_code for una in respuestas] == [200] * 6
    assert len({una.json()["access_token"] for una in respuestas}) == 6


async def test_entrar_no_mueve_la_version_del_usuario(backend_client):
    app, client = backend_client
    correo = await _cuenta(app)
    antes = await app.state.user_repository.get_by_email(correo)

    assert (await _entrar(client, correo)).status_code == 200

    despues = await app.state.user_repository.get_by_email(correo)
    assert despues.version == antes.version


async def test_entrar_deja_anotado_el_ultimo_acceso(backend_client):
    app, client = backend_client
    correo = await _cuenta(app)
    assert (await app.state.user_repository.get_by_email(correo)).last_access_at is None

    assert (await _entrar(client, correo)).status_code == 200

    assert (await app.state.user_repository.get_by_email(correo)).last_access_at is not None


async def test_el_ingreso_no_pisa_lo_que_otra_pantalla_acaba_de_cambiar(backend_client):
    app, client = backend_client
    correo = await _cuenta(app)
    usuario = await app.state.user_repository.get_by_email(correo)
    usuario.full_name = "Nombre corregido por administración"
    await app.state.user_repository.update(usuario)

    assert (await _entrar(client, correo)).status_code == 200

    despues = await app.state.user_repository.get_by_email(correo)
    assert despues.full_name == "Nombre corregido por administración"
