from __future__ import annotations

import pytest

from app.modules.identity_access.application.dto import RegisterUserCommand
from app.modules.identity_access.application.use_cases.create_user import CreateUser
from app.modules.identity_access.domain.value_objects import Role


async def authenticated_admin(client, app):
    await CreateUser(
        repository=app.state.user_repository,
        password_hasher=app.state.password_hasher,
        event_bus=app.state.event_bus,
    ).execute(
        RegisterUserCommand(
            email="frontend-contract@upchiapas.edu.mx",
            full_name="Frontend Contract",
            password="password-seguro",
            roles={Role.ADMIN_SISTEMA, Role.PLANEACION},
            area_id=None,
        )
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "correo": "frontend-contract@upchiapas.edu.mx",
            "contrasena": "password-seguro",
        },
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_frontend_indicator_detail_relations_and_filters(client, app):
    headers = await authenticated_admin(client, app)
    users = await client.get("/api/v1/usuarios?offset=0&limit=10", headers=headers)
    assert users.status_code == 200
    assert users.json()["total"] == 1
    assert users.json()["items"][0]["creado_en"]

    area = await client.post(
        "/api/v1/catalogos/areas",
        json={
            "codigo": "IBIO",
            "nombre": "Ingenieria Biomedica",
            "tipo": "programa_educativo",
            "color": "#01ADEF",
        },
        headers=headers,
    )
    assert area.json()["tipo"] == "programa_educativo"
    criterion = await client.post(
        "/api/v1/catalogos/criterios-seaes",
        json={"clave": "C1", "nombre": "Compromiso social"},
        headers=headers,
    )
    me = await client.get("/api/v1/auth/me", headers=headers)
    indicator = await client.post(
        "/api/v1/indicadores",
        json={
            "clave": "PIDE-01",
            "nombre": "Cobertura educativa",
            "metodo_calculo": "Resultado / meta * 100",
            "unidad_medida": "Porcentaje",
            "area_id": area.json()["id"],
            "responsable_id": me.json()["id"],
            "periodicidad": "mensual",
        },
        headers=headers,
    )
    indicator_id = indicator.json()["id"]
    linked = await client.put(
        f"/api/v1/indicadores/{indicator_id}/criterios-seaes",
        json={"criterio_ids": [criterion.json()["id"]]},
        headers=headers,
    )
    assert linked.json() == [criterion.json()["id"]]
    await client.post(
        f"/api/v1/indicadores/{indicator_id}/linea-base",
        json={"anio": 2025, "periodo": "Anual", "valor": "82.50"},
        headers=headers,
    )
    detail = await client.get(f"/api/v1/indicadores/{indicator_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["linea_base"]["valor"] == "82.50"
    assert detail.json()["criterio_seaes_ids"] == [criterion.json()["id"]]
    filtered = await client.get(
        f"/api/v1/indicadores?criterio_seaes_id={criterion.json()['id']}",
        headers=headers,
    )
    assert [item["id"] for item in filtered.json()["items"]] == [indicator_id]
    coverage = await client.get("/api/v1/indicadores/cobertura-seaes", headers=headers)
    assert coverage.json()["porcentaje_cobertura"] == "100.00"


@pytest.mark.asyncio
async def test_secure_upload_and_request_id_error_contract(client, app, tmp_path):
    app.state.settings.upload_directory = str(tmp_path)
    headers = await authenticated_admin(client, app)
    uploaded = await client.post(
        "/api/v1/archivos",
        files={"archivo": ("evidencia.pdf", b"%PDF-1.4\ncontract", "text/plain")},
        headers=headers,
    )
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["mime_type"] == "application/pdf"
    assert len(uploaded.json()["checksum_sha256"]) == 64

    missing = await client.get(
        "/api/v1/indicadores/999999",
        headers={**headers, "X-Request-ID": "frontend-contract-request"},
    )
    assert missing.status_code == 404
    assert missing.json()["request_id"] == "frontend-contract-request"
    assert missing.headers["X-Request-ID"] == "frontend-contract-request"
