from __future__ import annotations

import pytest

from app.modules.identity_access.application.dto import RegisterUserCommand
from app.modules.identity_access.application.use_cases.create_user import CreateUser
from app.modules.identity_access.domain.value_objects import Role


@pytest.mark.asyncio
async def test_poa_planning_tracking_validation_and_reports(client, app):
    await CreateUser(
        repository=app.state.user_repository,
        password_hasher=app.state.password_hasher,
        event_bus=app.state.event_bus,
    ).execute(
        RegisterUserCommand(
            email="poa-admin@upchiapas.edu.mx",
            full_name="Administrador POA",
            password="password-seguro",
            roles={Role.ADMIN_SISTEMA, Role.PLANEACION},
            area_id=None,
        )
    )
    login = await client.post(
        "/api/v1/auth/login",
        data={"username": "poa-admin@upchiapas.edu.mx", "password": "password-seguro"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    area = await client.post(
        "/api/v1/catalogos/areas",
        json={"codigo": "POA", "nombre": "Area POA"},
        headers=headers,
    )
    criterion = await client.post(
        "/api/v1/catalogos/criterios-seaes",
        json={"clave": "POA-CRIT", "nombre": "Criterio POA"},
        headers=headers,
    )
    exercise = await client.post(
        "/api/v1/poa/ejercicios",
        json={"anio": 2032},
        headers=headers,
    )
    process = await client.post(
        "/api/v1/poa/procesos",
        json={
            "ejercicio_id": exercise.json()["id"],
            "nombre": "Proceso institucional",
            "area_id": area.json()["id"],
        },
        headers=headers,
    )
    objective = await client.post(
        "/api/v1/poa/objetivos",
        json={"proceso_id": process.json()["id"], "objetivo": "Objetivo POA"},
        headers=headers,
    )
    activity = await client.post(
        "/api/v1/poa/actividades",
        json={
            "objetivo_id": objective.json()["id"],
            "descripcion": "Actividad anual",
            "unidad_medida": "Actividad",
            "meta_anual": 100,
            "responsable_id": (await client.get("/api/v1/auth/me", headers=headers)).json()["id"],
        },
        headers=headers,
    )
    period = await client.post(
        "/api/v1/periodos",
        json={
            "tipo": "poa",
            "periodicidad": None,
            "anio": 2032,
            "etiqueta": "POA 2032 C1",
            "fecha_inicio": "2032-01-01",
            "fecha_limite": "2032-04-30",
        },
        headers=headers,
    )
    await client.post(f"/api/v1/periodos/{period.json()['id']}/abrir", headers=headers)
    advance = await client.post(
        "/api/v1/poa/avances",
        json={
            "actividad_id": activity.json()["id"],
            "cuatrimestre": 1,
            "periodo_id": period.json()["id"],
            "programado": 50,
            "alcanzado": 45,
            "observaciones": "Avance del primer cuatrimestre",
            "criterio_seaes_ids": [criterion.json()["id"]],
        },
        headers=headers,
    )
    assert advance.status_code == 201, advance.text
    advance_id = advance.json()["id"]
    evidence = await client.post(
        f"/api/v1/poa/avances/{advance_id}/evidencias",
        json={
            "nombre": "Evidencia POA",
            "descripcion": "Evidencia del avance",
            "fecha": "2032-04-30",
            "tipo": "enlace",
            "ruta_o_url": "https://example.com/poa",
        },
        headers=headers,
    )
    assert evidence.status_code == 201, evidence.text
    sent = await client.post(f"/api/v1/poa/avances/{advance_id}/enviar", headers=headers)
    assert sent.status_code == 200, sent.text
    validated = await client.post(f"/api/v1/poa/avances/{advance_id}/validar", headers=headers)
    assert validated.status_code == 200, validated.text
    assert float(validated.json()["porcentaje_cumplimiento"]) == 90
    accumulated = await client.get(
        f"/api/v1/poa/actividades/{activity.json()['id']}/acumulado",
        headers=headers,
    )
    assert accumulated.status_code == 200
    assert accumulated.json()["disponible"] is True
    report = await client.get("/api/v1/poa/reportes/cuatrimestral", headers=headers)
    assert report.status_code == 200
    assert report.json()["tipo"] == "cuatrimestral"
