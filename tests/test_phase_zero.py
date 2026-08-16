from __future__ import annotations

import pytest

from app.modules.identity_access.application.dto import RegisterUserCommand
from app.modules.identity_access.application.use_cases.create_user import CreateUser
from app.modules.identity_access.domain.value_objects import Role


async def create_admin(app):
    return await CreateUser(
        repository=app.state.user_repository,
        password_hasher=app.state.password_hasher,
        event_bus=app.state.event_bus,
    ).execute(
        RegisterUserCommand(
            email="admin@upchiapas.edu.mx",
            full_name="Administrador de pruebas",
            password="password-seguro",
            roles={Role.ADMIN_SISTEMA},
            area_id=None,
        )
    )


@pytest.mark.asyncio
async def test_authentication_refresh_rotation_and_logout(client, app):
    await create_admin(app)

    login = await client.post(
        "/api/v1/auth/login",
        json={"correo": "admin@upchiapas.edu.mx", "contrasena": "password-seguro"},
    )
    assert login.status_code == 200
    tokens = login.json()
    assert tokens["token_type"] == "bearer"

    me = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["correo"] == "admin@upchiapas.edu.mx"

    refresh = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refresh.status_code == 200
    rotated = refresh.json()
    assert rotated["refresh_token"] != tokens["refresh_token"]

    reused = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert reused.status_code == 401

    session_revoked = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": rotated["refresh_token"]},
    )
    assert session_revoked.status_code == 401

    new_login = await client.post(
        "/api/v1/auth/login",
        json={"correo": "admin@upchiapas.edu.mx", "contrasena": "password-seguro"},
    )
    new_tokens = new_login.json()
    logout = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": new_tokens["refresh_token"]},
        headers={"Authorization": f"Bearer {new_tokens['access_token']}"},
    )
    assert logout.status_code == 204
    assert (
        await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {new_tokens['access_token']}"},
        )
    ).status_code == 401


@pytest.mark.asyncio
async def test_catalog_period_and_audit_flow(client, app):
    await create_admin(app)
    login = await client.post(
        "/api/v1/auth/login",
        json={"correo": "admin@upchiapas.edu.mx", "contrasena": "password-seguro"},
    )
    access_token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    area = await client.post(
        "/api/v1/catalogos/areas",
        json={"codigo": "DIP", "nombre": "Direccion de Planeacion"},
        headers=headers,
    )
    assert area.status_code == 201
    areas = await client.get("/api/v1/catalogos/areas", headers=headers)
    assert areas.json()[0]["codigo"] == "DIP"

    period = await client.post(
        "/api/v1/periodos",
        json={
            "tipo": "indicadores",
            "periodicidad": "mensual",
            "anio": 2026,
            "etiqueta": "Captura 2026",
            "fecha_inicio": "2026-01-01",
            "fecha_limite": "2026-04-30",
        },
        headers=headers,
    )
    assert period.status_code == 201
    period_id = period.json()["id"]

    opened = await client.post(f"/api/v1/periodos/{period_id}/abrir", headers=headers)
    assert opened.status_code == 200
    assert opened.json()["estado"] == "abierto"

    closed = await client.post(f"/api/v1/periodos/{period_id}/cerrar", headers=headers)
    assert closed.status_code == 200
    assert closed.json()["estado"] == "cerrado"

    reopened = await client.post(
        f"/api/v1/periodos/{period_id}/reabrir",
        json={"motivo": "Correccion autorizada"},
        headers=headers,
    )
    assert reopened.status_code == 200
    assert reopened.json()["estado"] == "abierto"

    audit = await client.get("/api/v1/auditoria", headers=headers)
    assert audit.status_code == 200
    event_names = {entry["evento"] for entry in audit.json()}
    assert "AreaCreated" in event_names
    assert "PeriodReopened" in event_names


@pytest.mark.asyncio
async def test_reopen_requires_reason(client, app):
    await create_admin(app)
    login = await client.post(
        "/api/v1/auth/login",
        json={"correo": "admin@upchiapas.edu.mx", "contrasena": "password-seguro"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    period = await client.post(
        "/api/v1/periodos",
        json={
            "tipo": "indicadores",
            "periodicidad": "mensual",
            "anio": 2027,
            "etiqueta": "Captura 2027",
            "fecha_inicio": "2027-01-01",
            "fecha_limite": "2027-04-30",
        },
        headers=headers,
    )
    period_id = period.json()["id"]
    await client.post(f"/api/v1/periodos/{period_id}/abrir", headers=headers)
    await client.post(f"/api/v1/periodos/{period_id}/cerrar", headers=headers)

    response = await client.post(
        f"/api/v1/periodos/{period_id}/reabrir",
        json={"motivo": "   "},
        headers=headers,
    )
    assert response.status_code == 422
