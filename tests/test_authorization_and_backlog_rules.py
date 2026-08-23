from __future__ import annotations

import pytest

from app.modules.identity_access.application.dto import RegisterUserCommand
from app.modules.identity_access.application.use_cases.create_user import CreateUser
from app.modules.identity_access.domain.value_objects import Role


async def create_user(app, email: str, roles: set[Role], area_id: int | None = None):
    return await CreateUser(
        repository=app.state.user_repository,
        password_hasher=app.state.password_hasher,
        event_bus=app.state.event_bus,
    ).execute(
        RegisterUserCommand(
            email=email,
            full_name=email.split("@")[0],
            password="password-seguro",
            roles=roles,
            area_id=area_id,
        )
    )


async def login(client, email: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login",
        json={"correo": email, "contrasena": "password-seguro"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.asyncio
async def test_resource_authorization_inmutability_reports_and_poa_assignment(client, app):
    await create_user(app, "admin@upchiapas.edu.mx", {Role.ADMIN_SISTEMA, Role.PLANEACION})
    admin_headers = await login(client, "admin@upchiapas.edu.mx")
    area_one = await client.post(
        "/api/v1/catalogos/areas",
        json={"codigo": "A1", "nombre": "Area uno"},
        headers=admin_headers,
    )
    area_two = await client.post(
        "/api/v1/catalogos/areas",
        json={"codigo": "A2", "nombre": "Area dos"},
        headers=admin_headers,
    )
    area_one_id = area_one.json()["id"]
    area_two_id = area_two.json()["id"]
    user_one = await create_user(
        app, "responsable1@upchiapas.edu.mx", {Role.RESPONSABLE_AREA}, area_one_id
    )
    user_two = await create_user(
        app, "responsable2@upchiapas.edu.mx", {Role.RESPONSABLE_AREA}, area_two_id
    )
    consultation = await create_user(
        app, "consulta@upchiapas.edu.mx", {Role.CONSULTA}, area_one_id
    )
    one_headers = await login(client, "responsable1@upchiapas.edu.mx")
    two_headers = await login(client, "responsable2@upchiapas.edu.mx")

    period = await client.post(
        "/api/v1/periodos",
        json={
            "tipo": "indicadores",
            "periodicidad": "mensual",
            "anio": 2035,
            "etiqueta": "Enero 2035",
            "fecha_inicio": "2035-01-01",
            "fecha_limite": "2035-01-31",
        },
        headers=admin_headers,
    )
    period_id = period.json()["id"]

    invalid_assignment = await client.post(
        "/api/v1/indicadores",
        json={
            "clave": "AUTH-INVALID",
            "nombre": "Asignacion invalida",
            "metodo_calculo": "Resultado / meta",
            "unidad_medida": "Porcentaje",
            "area_id": area_one_id,
            "responsable_id": consultation.id,
            "periodicidad": "mensual",
        },
        headers=admin_headers,
    )
    assert invalid_assignment.status_code == 422

    async def indicator(key: str, area_id: int, responsible_id: int) -> int:
        response = await client.post(
            "/api/v1/indicadores",
            json={
                "clave": key,
                "nombre": f"Indicador {key}",
                "metodo_calculo": "Resultado / meta",
                "unidad_medida": "Porcentaje",
                "area_id": area_id,
                "responsable_id": responsible_id,
                "periodicidad": "mensual",
            },
            headers=admin_headers,
        )
        assert response.status_code == 201, response.text
        indicator_id = response.json()["id"]
        goal = await client.post(
            f"/api/v1/indicadores/{indicator_id}/metas",
            json={"periodo_id": period_id, "valor": 100},
            headers=admin_headers,
        )
        assert goal.status_code == 201, goal.text
        return indicator_id

    indicator_one = await indicator("AUTH-01", area_one_id, user_one.id)
    indicator_two = await indicator("AUTH-02", area_two_id, user_two.id)
    opened = await client.post(
        f"/api/v1/periodos/{period_id}/abrir", headers=admin_headers
    )
    assert opened.status_code == 200, opened.text

    capture = await client.post(
        "/api/v1/capturas",
        json={"indicador_id": indicator_one, "periodo_id": period_id, "resultado": 90},
        headers=one_headers,
    )
    capture_id = capture.json()["id"]
    evidence = await client.post(
        "/api/v1/evidencias",
        json={
            "nombre": "Evidencia",
            "descripcion": "Documento de respaldo",
            "fecha": "2035-01-20",
            "tipo": "enlace",
            "ruta_o_url": "https://example.com/evidencia",
            "entidad": "captura",
            "entidad_id": capture_id,
        },
        headers=one_headers,
    )
    assert evidence.status_code == 201, evidence.text
    evidence_id = evidence.json()["id"]

    assert (
        await client.get(f"/api/v1/capturas/{capture_id}", headers=two_headers)
    ).status_code == 403
    foreign_attach = await client.post(
        "/api/v1/evidencias",
        json={
            "nombre": "Ajena",
            "descripcion": "No debe permitirse",
            "fecha": "2035-01-20",
            "tipo": "enlace",
            "ruta_o_url": "https://example.com/ajena",
            "entidad": "captura",
            "entidad_id": capture_id,
        },
        headers=two_headers,
    )
    assert foreign_attach.status_code == 403
    assert (
        await client.get(f"/api/v1/evidencias/{evidence_id}/versiones", headers=two_headers)
    ).status_code == 403
    assert (
        await client.get(
            f"/api/v1/indicadores/{indicator_one}/historial", headers=two_headers
        )
    ).status_code == 403

    sent = await client.post(f"/api/v1/capturas/{capture_id}/enviar", headers=one_headers)
    assert sent.status_code == 200, sent.text
    validated = await client.post(
        f"/api/v1/capturas/{capture_id}/validar", headers=admin_headers
    )
    assert validated.status_code == 200, validated.text
    immutable = await client.post(
        f"/api/v1/capturas/{capture_id}/evidencias",
        json={
            "nombre": "Tardia",
            "descripcion": "No debe cambiar una captura validada",
            "fecha": "2035-01-21",
            "tipo": "enlace",
            "ruta_o_url": "https://example.com/tardia",
        },
        headers=one_headers,
    )
    assert immutable.status_code == 409
    assert immutable.json()["code"] == "CAPTURE_IMMUTABLE"
    immutable_unlink = await client.delete(
        f"/api/v1/capturas/{capture_id}/evidencias/{evidence_id}", headers=one_headers
    )
    assert immutable_unlink.status_code == 409
    assert immutable_unlink.json()["code"] == "CAPTURE_IMMUTABLE"

    own_report = await client.get(
        f"/api/v1/reportes/por-area?area_id={area_two_id}&periodo_id={period_id}",
        headers=one_headers,
    )
    assert own_report.status_code == 200, own_report.text
    assert {row["indicador_id"] for row in own_report.json()["filas"]} == {indicator_one}
    assert (
        await client.get("/api/v1/reportes/institucional", headers=one_headers)
    ).status_code == 403
    missing = await client.get(
        f"/api/v1/reportes/sin-captura?periodo_id={period_id}", headers=admin_headers
    )
    assert {row["indicador_id"] for row in missing.json()["filas"]} == {indicator_two}
    assert (
        await client.post(f"/api/v1/periodos/{period_id}/cerrar", headers=admin_headers)
    ).status_code == 200
    reopened = await client.post(
        f"/api/v1/periodos/{period_id}/reabrir",
        json={"motivo": "Correccion formal autorizada"},
        headers=admin_headers,
    )
    assert reopened.status_code == 200, reopened.text
    corrected = await client.patch(
        f"/api/v1/capturas/{capture_id}",
        json={"resultado": 95, "observaciones": "Corregido tras reapertura"},
        headers=one_headers,
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["estado"] == "borrador"
    history = await client.get(
        f"/api/v1/capturas/{capture_id}/historial", headers=one_headers
    )
    assert history.status_code == 200
    assert history.json()["items"][0]["de_estado"] == "validado"
    assert history.json()["items"][0]["a_estado"] == "borrador"
    assert history.json()["items"][0]["comentario"].startswith("Reapertura:")

    exercise = await client.post(
        "/api/v1/poa/ejercicios", json={"anio": 2035}, headers=admin_headers
    )
    process = await client.post(
        "/api/v1/poa/procesos",
        json={
            "ejercicio_id": exercise.json()["id"],
            "nombre": "Proceso area uno",
            "area_id": area_one_id,
        },
        headers=admin_headers,
    )
    objective = await client.post(
        "/api/v1/poa/objetivos",
        json={"proceso_id": process.json()["id"], "objetivo": "Objetivo seguro"},
        headers=admin_headers,
    )
    invalid_poa_assignment = await client.post(
        "/api/v1/poa/actividades",
        json={
            "objetivo_id": objective.json()["id"],
            "descripcion": "Actividad sin rol operativo",
            "unidad_medida": "Actividad",
            "meta_anual": 1,
            "responsable_id": consultation.id,
        },
        headers=admin_headers,
    )
    assert invalid_poa_assignment.status_code == 422
    activity = await client.post(
        "/api/v1/poa/actividades",
        json={
            "objetivo_id": objective.json()["id"],
            "descripcion": "Actividad asignada",
            "unidad_medida": "Actividad",
            "meta_anual": 10,
            "responsable_id": user_one.id,
        },
        headers=admin_headers,
    )
    poa_period = await client.post(
        "/api/v1/periodos",
        json={
            "tipo": "poa",
            "periodicidad": None,
            "anio": 2035,
            "etiqueta": "POA 2035 C1",
            "fecha_inicio": "2035-01-01",
            "fecha_limite": "2035-04-30",
        },
        headers=admin_headers,
    )
    await client.post(
        f"/api/v1/periodos/{poa_period.json()['id']}/abrir", headers=admin_headers
    )
    foreign_advance = await client.post(
        "/api/v1/poa/avances",
        json={
            "actividad_id": activity.json()["id"],
            "cuatrimestre": 1,
            "periodo_id": poa_period.json()["id"],
            "programado": 5,
            "alcanzado": 4,
            "observaciones": "Intento ajeno",
            "criterio_seaes_ids": [],
        },
        headers=two_headers,
    )
    assert foreign_advance.status_code == 403
