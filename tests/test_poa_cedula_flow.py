from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from app.modules.identity_access.application.dto import RegisterUserCommand
from app.modules.identity_access.application.use_cases.create_user import CreateUser
from app.modules.identity_access.domain.value_objects import Role
from app.modules.poa_planning.infrastructure.reference_data import (
    POA_ACTIVITIES,
    POA_INDICATORS,
    POA_OBJECTIVES,
    POA_STRATEGIES,
)


@pytest.mark.asyncio
async def test_multiple_children_area_permissions_and_snapshots(backend_client):
    app, client = backend_client
    suffix = uuid4().hex[:8]

    async def account(role, area_id=None):
        email = f"{role.value}-{suffix}@example.com"
        user = await CreateUser(
            app.state.user_repository, app.state.password_hasher, app.state.event_bus
        ).execute(
            RegisterUserCommand(
                email=email,
                full_name=role.value,
                password="password-seguro",
                roles={role},
                area_id=area_id,
            )
        )
        login = await client.post(
            "/api/v1/auth/login",
            json={
                "correo": email,
                "contrasena": "password-seguro",
            },
        )
        assert login.status_code == 200, login.text
        return user, {"Authorization": f"Bearer {login.json()['access_token']}"}

    admin, headers = await account(Role.ADMIN_SISTEMA)
    area = await client.post(
        "/api/v1/catalogos/areas",
        headers=headers,
        json={
            "codigo": f"MULTI-{suffix}",
            "nombre": f"Área ejecutora {suffix}",
        },
    )
    assert area.status_code == 201, area.text
    area_id = area.json()["id"]
    capturer, capturer_headers = await account(Role.CAPTURISTA_POA, area_id)
    _, reviewer_headers = await account(Role.REVISOR_POA, area_id)
    planner, planner_headers = await account(Role.PLANEACION)
    exercise = await client.post("/api/v1/poa/ejercicios", headers=headers, json={"anio": 2197})
    assert exercise.status_code == 201, exercise.text
    response = await client.post(
        "/api/v1/poa/cedulas",
        headers=headers,
        json={
            "ejercicio_id": exercise.json()["id"],
            "estrategia_clave": "6.1",
            "area_responsable_id": area_id,
            "tipo_estrategia": "Vinculación",
            "firmantes": [
                {"nombre": "Titular Rectoría", "cargo": "Rectoría"},
                {"nombre": "Titular Secretaría", "cargo": "Secretaría Académica"},
            ],
            "cuatrimestres": [
                {"numero": 1, "fecha_inicio": "2197-01-01", "fecha_fin": "2197-04-30"},
                {"numero": 2, "fecha_inicio": "2197-05-01", "fecha_fin": "2197-08-31"},
                {"numero": 3, "fecha_inicio": "2197-09-01", "fecha_fin": "2197-12-31"},
            ],
        },
    )
    assert response.status_code == 201, response.text
    form_id = response.json()["id"]
    period_id = response.json()["cuatrimestres"][0]["periodo_id"]
    form_url = f"/api/v1/poa/cedulas/{form_id}"
    for key in ("6.1.2", "6.1.3"):
        response = await client.post(
            f"{form_url}/indicadores",
            headers=headers,
            json={
                "indicador_clave": key,
                "numero_a_lograr": 100,
            },
        )
        assert response.status_code == 201, response.text
    duplicate = await client.post(
        f"{form_url}/indicadores",
        headers=headers,
        json={
            "indicador_clave": "6.1.2",
        },
    )
    assert duplicate.status_code == 409, duplicate.text
    activities = []
    for key in ("6.1.1", "6.1.2"):
        response = await client.post(
            f"{form_url}/actividades",
            headers=headers,
            json={
                "actividad_clave": key,
                "area_ejecutora_id": area_id,
                "meta_anual": 100,
                "unidad_medida": "Eventos",
            },
        )
        assert response.status_code == 201, response.text
        activities.append(response.json()["id"])
    duplicate = await client.post(
        f"{form_url}/actividades",
        headers=headers,
        json={
            "actividad_clave": "6.1.1",
            "meta_anual": 100,
            "unidad_medida": "Eventos",
        },
    )
    assert duplicate.status_code == 409, duplicate.text
    for url in (form_url,):
        blocked = await client.patch(
            url,
            headers=capturer_headers,
            json={
                "alcance_efecto_socioeconomico": "No debe cambiar",
            },
        )
        assert blocked.status_code == 403, blocked.text
    blocked = await client.get(form_url, headers=reviewer_headers)
    assert blocked.status_code == 403, blocked.text
    detail = await client.get(form_url, headers=capturer_headers)
    assert detail.status_code == 200, detail.text
    assert len(detail.json()["indicadores"]) == 2
    assert len(detail.json()["actividades"]) == 2

    # Planeación no administrativa no puede promoverse ni manipular administradores.
    for target in (admin, planner):
        denied = await client.patch(
            f"/api/v1/usuarios/{target.id}",
            headers=planner_headers,
            json={"roles": ["admin_sistema"]},
        )
        assert denied.status_code == 403, denied.text
    for email in (f"new-admin-{suffix}@example.com", "planeacion@upchiapas.edu.mx"):
        denied = await client.post(
            "/api/v1/usuarios",
            headers=planner_headers,
            json={
                "correo": email,
                "nombre": "Invitación",
                "roles": ["admin_sistema"],
            },
        )
        assert denied.status_code == 403, denied.text

    await _open_poa_period(client, headers, period_id)
    first_evidence_id = None
    for index, activity_id in enumerate(activities):
        follow_up = await client.put(
            f"/api/v1/poa/cedulas/actividades/{activity_id}/seguimientos/1",
            headers=capturer_headers,
            json={
                "periodo_id": period_id,
                "programado": 40,
                "alcanzado": 30,
                "progreso": "Actividades realizadas",
                "alcance": "Comunidad universitaria",
            },
        )
        assert follow_up.status_code == 200, follow_up.text
        evidence = await _attach_follow_up_file(
            client, capturer_headers, follow_up.json()["id"], f"multiple-{index}", "2197-04-30"
        )
        if index == 0:
            first_evidence_id = evidence.json()["id"]
            incomplete = await client.post(
                f"{form_url}/emisiones",
                headers=headers,
                json={
                    "cuatrimestre": 1,
                    "periodo_id": period_id,
                },
            )
            assert incomplete.status_code == 422, incomplete.text
    issue = await client.post(
        f"{form_url}/emisiones",
        headers=headers,
        json={
            "cuatrimestre": 1,
            "periodo_id": period_id,
        },
    )
    assert issue.status_code == 201, issue.text
    snapshot = issue.json()["snapshot"]
    assert snapshot["encabezado"]["anio"] == 2197
    assert snapshot["encabezado"]["tipo_estrategia"] == "Vinculación"
    assert len(snapshot["bloque_firmas"]) == 2
    assert snapshot["seccion_1_estrategia"]["area_responsable_nombre"] == f"Área ejecutora {suffix}"
    assert len(snapshot["seccion_2_indicadores"]) == 2
    assert len(snapshot["seccion_4_calendarizacion_y_seguimiento"]) == 2

    report = await client.get(
        f"/api/v1/poa/reportes/cuatrimestral?cedula_id={form_id}&periodo_id={period_id}",
        headers=headers,
    )
    assert report.status_code == 200, report.text
    assert len(report.json()["filas"]) == 2
    assert {row["actividad_id"] for row in report.json()["filas"]} == set(activities)
    assert report.json()["filtros"]["fuente"] == "cedulas_actuales"
    assert all("proceso_id" not in row for row in report.json()["filas"])
    missing = await client.get(
        f"/api/v1/poa/reportes/evidencias-faltantes?cedula_id={form_id}&periodo_id={period_id}",
        headers=headers,
    )
    assert missing.status_code == 200, missing.text
    assert missing.json()["filas"] == []
    future_missing = await client.get(
        f"/api/v1/poa/reportes/evidencias-faltantes?cedula_id={form_id}", headers=headers
    )
    assert len(future_missing.json()["filas"]) == 4  # Dos actividades pendientes en C2/C3.
    bad_filter = await client.get(
        "/api/v1/poa/reportes/cuatrimestral?proceso_id=1", headers=headers
    )
    assert bad_filter.status_code == 422
    for format_, magic in (("xlsx", b"PK"), ("pdf", b"%PDF")):
        exported = await client.get(
            f"/api/v1/poa/reportes/por-cedula?cedula_id={form_id}&formato={format_}",
            headers=headers,
        )
        assert exported.status_code == 200, exported.text[:100]
        assert exported.content.startswith(magic)
    dashboard = await client.get(
        f"/api/v1/dashboards/planeacion?periodo_id={period_id}", headers=headers
    )
    assert dashboard.status_code == 200, dashboard.text
    assert {row["actividad_id"] for row in dashboard.json()["poa"]} == set(activities)
    assert "avances_poa_por_estado" not in dashboard.json()["resumen"]
    history = await client.get(
        f"/api/v1/poa/cedulas/actividades/{activities[0]}/historial", headers=capturer_headers
    )
    assert history.status_code == 200, history.text
    assert history.json()["total"] >= 1
    for url in ("/api/v1/poa/reportes/ejecutivo", "/api/v1/poa/cedulas"):
        assert (await client.get(url, headers=reviewer_headers)).status_code == 403

    # La pertenencia anterior o ser quien subió el archivo no conserva permiso tras reasignación.
    new_area = await client.post(
        "/api/v1/catalogos/areas",
        headers=headers,
        json={
            "codigo": f"OTRA-{suffix}",
            "nombre": f"Área nueva {suffix}",
        },
    )
    reassigned = await client.patch(
        f"/api/v1/usuarios/{capturer.id}", headers=headers, json={"area_id": new_area.json()["id"]}
    )
    duplicate_target = await client.post(
        "/api/v1/poa/cedulas",
        headers=headers,
        json={
            "ejercicio_id": exercise.json()["id"],
            "estrategia_clave": "6.1",
            "area_responsable_id": new_area.json()["id"],
            "cuatrimestres": [
                {"numero": 1, "fecha_inicio": "2197-01-01", "fecha_fin": "2197-04-30"},
                {"numero": 2, "fecha_inicio": "2197-05-01", "fecha_fin": "2197-08-31"},
                {"numero": 3, "fecha_inicio": "2197-09-01", "fecha_fin": "2197-12-31"},
            ],
        },
    )
    assert duplicate_target.status_code == 201, duplicate_target.text
    conflict = await client.patch(
        form_url, headers=headers, json={"area_responsable_id": new_area.json()["id"]}
    )
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["details"]["reason"] == "POA_FORM_DUPLICATE"
    preserved = await client.get(form_url, headers=headers)
    assert preserved.json()["area_responsable_id"] == area_id
    assert reassigned.status_code == 200, reassigned.text
    scoped_report = await client.get(
        f"/api/v1/poa/reportes/por-area?area_id={area_id}", headers=capturer_headers
    )
    assert scoped_report.status_code == 200, scoped_report.text
    assert scoped_report.json()["filas"] == []
    denied = await client.get(
        f"/api/v1/evidencias/{first_evidence_id}/versiones", headers=capturer_headers
    )
    assert denied.status_code == 403, denied.text
    saved = await client.get(f"/api/v1/poa/emisiones/{issue.json()['id']}", headers=headers)
    assert saved.json()["snapshot"] == snapshot


def test_poa_reference_catalog_integrity():
    assert len(POA_OBJECTIVES) == 6
    assert len(POA_STRATEGIES) == 24
    assert len(POA_INDICATORS) == 11
    assert len(POA_ACTIVITIES) == 150

    objective_numbers = {item["numero"] for item in POA_OBJECTIVES}
    strategy_keys = {item["clave"] for item in POA_STRATEGIES}
    assert all(item["objetivo_numero"] in objective_numbers for item in POA_STRATEGIES)
    assert all(
        item["objetivo_numero"] == int(str(item["clave"]).split(".")[0]) for item in POA_INDICATORS
    )
    assert all(item["estrategia_clave"] in strategy_keys for item in POA_ACTIVITIES)


async def _open_poa_period(client, headers, period_id: int) -> None:
    opened = await client.post(f"/api/v1/periodos/{period_id}/abrir", headers=headers)
    assert opened.status_code == 200, opened.text


async def _attach_follow_up_file(
    client, headers, follow_up_id: int, label: str, evidence_date: str
):
    uploaded = await client.post(
        "/api/v1/archivos",
        files={
            "archivo": (
                f"{label}.pdf",
                b"%PDF-1.4\n% test evidence\n",
                "application/pdf",
            )
        },
        headers=headers,
    )
    assert uploaded.status_code == 201, uploaded.text
    file_data = uploaded.json()
    evidence = await client.post(
        "/api/v1/evidencias",
        json={
            "nombre": f"Informe {label}",
            "descripcion": "Respaldo del progreso y alcance reportados",
            "fecha": evidence_date,
            "tipo": "archivo",
            "ruta_o_url": file_data["ruta"],
            "mime_type": file_data["mime_type"],
            "tamanio_bytes": file_data["tamanio_bytes"],
            "checksum_sha256": file_data["checksum_sha256"],
            "entidad": "poa_cedula_seguimiento",
            "entidad_id": follow_up_id,
        },
        headers=headers,
    )
    assert evidence.status_code == 201, evidence.text
    return evidence


@pytest.mark.asyncio
async def test_poa_form_catalogs_quarters_and_immutable_issues(client, app, monkeypatch):
    await CreateUser(
        repository=app.state.user_repository,
        password_hasher=app.state.password_hasher,
        event_bus=app.state.event_bus,
    ).execute(
        RegisterUserCommand(
            email="cedula-poa@upchiapas.edu.mx",
            full_name="Planeación POA",
            password="password-seguro",
            roles={Role.ADMIN_SISTEMA, Role.PLANEACION},
            area_id=None,
        )
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"correo": "cedula-poa@upchiapas.edu.mx", "contrasena": "password-seguro"},
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    area = await client.post(
        "/api/v1/catalogos/areas",
        json={"codigo": "CED-POA", "nombre": "Área responsable de cédula"},
        headers=headers,
    )
    assert area.status_code == 201, area.text
    area_id = area.json()["id"]
    other_area = await client.post(
        "/api/v1/catalogos/areas",
        json={"codigo": "CED-OTRA", "nombre": "Otra área"},
        headers=headers,
    )
    assert other_area.status_code == 201, other_area.text
    for email, assigned_area_id in (
        ("capturista-cedula@upchiapas.edu.mx", area_id),
        ("capturista-otra@upchiapas.edu.mx", other_area.json()["id"]),
    ):
        await CreateUser(
            repository=app.state.user_repository,
            password_hasher=app.state.password_hasher,
            event_bus=app.state.event_bus,
        ).execute(
            RegisterUserCommand(
                email=email,
                full_name="Capturista POA",
                password="password-seguro",
                roles={Role.CAPTURISTA_POA},
                area_id=assigned_area_id,
            )
        )
    await CreateUser(
        repository=app.state.user_repository,
        password_hasher=app.state.password_hasher,
        event_bus=app.state.event_bus,
    ).execute(
        RegisterUserCommand(
            email="planeacion-edicion@upchiapas.edu.mx",
            full_name="Planeación",
            password="password-seguro",
            roles={Role.PLANEACION},
            area_id=None,
        )
    )
    capturer_login = await client.post(
        "/api/v1/auth/login",
        json={
            "correo": "capturista-cedula@upchiapas.edu.mx",
            "contrasena": "password-seguro",
        },
    )
    other_login = await client.post(
        "/api/v1/auth/login",
        json={
            "correo": "capturista-otra@upchiapas.edu.mx",
            "contrasena": "password-seguro",
        },
    )
    planning_login = await client.post(
        "/api/v1/auth/login",
        json={
            "correo": "planeacion-edicion@upchiapas.edu.mx",
            "contrasena": "password-seguro",
        },
    )
    capturer_headers = {"Authorization": f"Bearer {capturer_login.json()['access_token']}"}
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}
    planning_headers = {"Authorization": f"Bearer {planning_login.json()['access_token']}"}
    exercise = await client.post(
        "/api/v1/poa/ejercicios",
        json={"anio": 2036},
        headers=headers,
    )
    assert exercise.status_code == 201, exercise.text

    strategies = await client.get(
        "/api/v1/poa/catalogos/estrategias?objetivo_numero=6",
        headers=headers,
    )
    assert strategies.status_code == 200, strategies.text
    assert [item["clave"] for item in strategies.json()] == ["6.1", "6.2", "6.3", "6.4"]

    indicators = await client.get(
        "/api/v1/poa/catalogos/indicadores?objetivo_numero=6",
        headers=headers,
    )
    assert indicators.status_code == 200, indicators.text
    assert {item["clave"] for item in indicators.json()} == {"6.1.2", "6.1.3"}
    assert all(item["formula"] and item["unidad_medida"] for item in indicators.json())

    activities = await client.get(
        "/api/v1/poa/catalogos/actividades?estrategia_clave=6.1",
        headers=headers,
    )
    assert activities.status_code == 200, activities.text
    assert [item["clave"] for item in activities.json()] == [
        "6.1.1",
        "6.1.2",
        "6.1.3",
        "6.1.4",
        "6.1.5",
        "6.1.7",
        "6.1.8",
        "6.1.9",
        "6.1.10",
    ]

    form = await client.post(
        "/api/v1/poa/cedulas",
        json={
            "ejercicio_id": exercise.json()["id"],
            "estrategia_clave": "6.1",
            "area_responsable_id": area_id,
            "alcance_efecto_socioeconomico": "Comunidad universitaria",
            "tipo_estrategia": "Vinculación",
            "firmantes": [
                {"nombre": "Titular Rectoría", "cargo": "Rectoría"},
                {"nombre": "Titular Secretaría", "cargo": "Secretaría Académica"},
            ],
            "cuatrimestres": [
                {
                    "numero": 1,
                    "fecha_inicio": "2036-01-01",
                    "fecha_fin": "2036-04-30",
                },
                {
                    "numero": 2,
                    "fecha_inicio": "2036-05-01",
                    "fecha_fin": "2036-08-31",
                },
                {
                    "numero": 3,
                    "fecha_inicio": "2036-09-01",
                    "fecha_fin": "2036-12-31",
                },
            ],
        },
        headers=headers,
    )
    assert form.status_code == 201, form.text
    form_id = form.json()["id"]
    assert form.json()["objetivo_numero"] == 6
    periods = {item["numero"]: item["periodo_id"] for item in form.json()["cuatrimestres"]}

    wrong_indicator = await client.post(
        f"/api/v1/poa/cedulas/{form_id}/indicadores",
        json={"indicador_clave": "5.1"},
        headers=headers,
    )
    assert wrong_indicator.status_code == 422, wrong_indicator.text

    indicator = await client.post(
        f"/api/v1/poa/cedulas/{form_id}/indicadores",
        json={
            "indicador_clave": "6.1.2",
            "meta_institucional": 80,
            "linea_base_anio": 2035,
            "linea_base_valor": 60,
            "porcentaje_actual": 60,
            "numero_a_lograr": 100,
            "porcentaje_a_lograr": 80,
        },
        headers=headers,
    )
    assert indicator.status_code == 201, indicator.text
    indicator_id = indicator.json()["id"]

    monkeypatch.setattr(
        "app.modules.poa_planning.application.use_cases.manage_cedula._today",
        lambda: date(2036, 4, 30),
    )
    editable_form_on_last_day = await client.patch(
        f"/api/v1/poa/cedulas/{form_id}",
        json={"alcance_efecto_socioeconomico": "Cobertura universitaria actualizada"},
        headers=planning_headers,
    )
    assert editable_form_on_last_day.status_code == 200, editable_form_on_last_day.text
    editable_on_last_day = await client.patch(
        f"/api/v1/poa/cedulas/indicadores/{indicator_id}",
        json={"porcentaje_a_lograr": 81},
        headers=planning_headers,
    )
    assert editable_on_last_day.status_code == 200, editable_on_last_day.text
    monkeypatch.setattr(
        "app.modules.poa_planning.application.use_cases.manage_cedula._today",
        lambda: date(2036, 5, 1),
    )
    locked_after_first_quarter = await client.patch(
        f"/api/v1/poa/cedulas/indicadores/{indicator_id}",
        json={"porcentaje_a_lograr": 82},
        headers=planning_headers,
    )
    assert locked_after_first_quarter.status_code == 422
    locked_form = await client.patch(
        f"/api/v1/poa/cedulas/{form_id}",
        json={"alcance_efecto_socioeconomico": "Cambio fuera de fecha"},
        headers=planning_headers,
    )
    assert locked_form.status_code == 422, locked_form.text
    emergency_admin_edit = await client.patch(
        f"/api/v1/poa/cedulas/indicadores/{indicator_id}",
        json={"porcentaje_a_lograr": 80},
        headers=headers,
    )
    assert emergency_admin_edit.status_code == 200, emergency_admin_edit.text

    activity = await client.post(
        f"/api/v1/poa/cedulas/{form_id}/actividades",
        json={
            "actividad_clave": "6.1.5",
            "unidad_medida": "Evento",
            "meta_anual": 100,
            "area_ejecutora_id": area_id,
        },
        headers=headers,
    )
    assert activity.status_code == 201, activity.text
    activity_id = activity.json()["id"]
    emergency_activity_edit = await client.patch(
        f"/api/v1/poa/cedulas/actividades/{activity_id}",
        json={"unidad_medida": "Eventos"},
        headers=headers,
    )
    assert emergency_activity_edit.status_code == 200, emergency_activity_edit.text

    q1_period_id = periods[1]
    await _open_poa_period(client, headers, q1_period_id)
    early_total = await client.patch(
        f"/api/v1/poa/cedulas/indicadores/{indicator_id}/total-alcanzado",
        json={"periodo_id": q1_period_id, "total_alcanzado": 35, "porcentaje_alcanzado": 35},
        headers=headers,
    )
    assert early_total.status_code == 422, early_total.text

    forbidden_follow_up = await client.put(
        f"/api/v1/poa/cedulas/actividades/{activity_id}/seguimientos/1",
        json={"periodo_id": q1_period_id, "programado": 40},
        headers=other_headers,
    )
    assert forbidden_follow_up.status_code == 403, forbidden_follow_up.text

    pending_follow_up = await client.put(
        f"/api/v1/poa/cedulas/actividades/{activity_id}/seguimientos/1",
        json={"periodo_id": q1_period_id, "programado": 40},
        headers=capturer_headers,
    )
    assert pending_follow_up.status_code == 200, pending_follow_up.text
    incomplete_issue = await client.post(
        f"/api/v1/poa/cedulas/{form_id}/emisiones",
        json={"cuatrimestre": 1, "periodo_id": q1_period_id},
        headers=headers,
    )
    assert incomplete_issue.status_code == 422, incomplete_issue.text

    q1_follow_up = await client.put(
        f"/api/v1/poa/cedulas/actividades/{activity_id}/seguimientos/1",
        json={
            "periodo_id": q1_period_id,
            "programado": 40,
            "alcanzado": 35,
            "justificacion_desviacion": "Ajuste de calendario",
            "progreso": "Se realizaron 35 eventos.",
            "alcance": "Participó la comunidad universitaria.",
        },
        headers=capturer_headers,
    )
    assert q1_follow_up.status_code == 200, q1_follow_up.text
    assert q1_follow_up.json()["programado_porcentaje"] == "40.00"

    improved_justification = await client.patch(
        f"/api/v1/poa/cedulas/seguimientos/{q1_follow_up.json()['id']}/justificacion",
        json={
            "justificacion_desviacion": (
                "La diferencia obedece al ajuste formal del calendario institucional."
            )
        },
        headers=planning_headers,
    )
    assert improved_justification.status_code == 200, improved_justification.text

    evidence = await _attach_follow_up_file(
        client,
        capturer_headers,
        q1_follow_up.json()["id"],
        "primer cuatrimestre",
        "2036-04-30",
    )
    assert evidence.status_code == 201, evidence.text

    q1_issue = await client.post(
        f"/api/v1/poa/cedulas/{form_id}/emisiones",
        json={"cuatrimestre": 1, "periodo_id": q1_period_id},
        headers=headers,
    )
    assert q1_issue.status_code == 201, q1_issue.text
    assert q1_issue.json()["nombre"] == "Cédula Objetivo 6 - Enero-Abril 2036"
    q1_issue_id = q1_issue.json()["id"]
    snapshot = q1_issue.json()["snapshot"]
    assert snapshot["seccion_2_indicadores"][0]["catalogo"]["formula"]
    assert snapshot["seccion_4_calendarizacion_y_seguimiento"][0]["catalogo"]["description"]
    assert (
        snapshot["seccion_4_calendarizacion_y_seguimiento"][0]["seguimientos"][0]["achieved"]
        == "35"
    )

    changed_follow_up = await client.put(
        f"/api/v1/poa/cedulas/actividades/{activity_id}/seguimientos/1",
        json={
            "periodo_id": q1_period_id,
            "programado": 40,
            "alcanzado": 39,
            "progreso": "Se realizaron 39 eventos.",
            "alcance": "Participó la comunidad universitaria.",
        },
        headers=headers,
    )
    assert changed_follow_up.status_code == 200, changed_follow_up.text
    saved_issue = await client.get(f"/api/v1/poa/emisiones/{q1_issue_id}", headers=headers)
    assert saved_issue.status_code == 200, saved_issue.text
    assert (
        saved_issue.json()["snapshot"]["seccion_4_calendarizacion_y_seguimiento"][0][
            "seguimientos"
        ][0]["achieved"]
        == "35"
    )

    duplicate_issue = await client.post(
        f"/api/v1/poa/cedulas/{form_id}/emisiones",
        json={"cuatrimestre": 1, "periodo_id": q1_period_id},
        headers=headers,
    )
    assert duplicate_issue.status_code == 409, duplicate_issue.text

    q3_period_id = periods[3]
    await _open_poa_period(client, headers, q3_period_id)
    total_url = f"/api/v1/poa/cedulas/indicadores/{indicator_id}/total-alcanzado"
    total_body = {"periodo_id": q3_period_id, "total_alcanzado": 120, "porcentaje_alcanzado": 37}
    # Abrir C3 anticipadamente no permite saltar el calendario, ni siquiera al administrador.
    early = await client.patch(total_url, headers=headers, json=total_body)
    assert early.status_code == 422, early.text
    assert early.json()["details"]["reason"] == "POA_TOTAL_OUTSIDE_WINDOW"
    assert early.json()["details"]["fecha_inicio"] == "2036-09-01"
    for day, expected in (
        (date(2036, 8, 31), 422),
        (date(2036, 9, 1), 200),
        (date(2036, 12, 31), 200),
        (date(2037, 1, 1), 422),
    ):
        monkeypatch.setattr(
            "app.modules.poa_planning.application.use_cases.manage_cedula._today", lambda: day
        )
        result = await client.patch(total_url, headers=planning_headers, json=total_body)
        assert result.status_code == expected, result.text
        if expected == 200:
            assert Decimal(result.json()["porcentaje_alcanzado"]) == Decimal(37)
    monkeypatch.setattr(
        "app.modules.poa_planning.application.use_cases.manage_cedula._today",
        lambda: date(2036, 9, 1),
    )
    denied_total = await client.patch(total_url, headers=capturer_headers, json=total_body)
    assert denied_total.status_code == 403, denied_total.text
    missing_percentage = await client.patch(
        total_url, headers=headers, json={"periodo_id": q3_period_id, "total_alcanzado": 120}
    )
    assert missing_percentage.status_code == 422
    total = await client.patch(
        f"/api/v1/poa/cedulas/indicadores/{indicator_id}/total-alcanzado",
        json={"periodo_id": q3_period_id, "total_alcanzado": 120, "porcentaje_alcanzado": 120},
        headers=headers,
    )
    assert total.status_code == 200, total.text
    assert Decimal(total.json()["porcentaje_alcanzado"]) == Decimal("120")

    q3_follow_up = await client.put(
        f"/api/v1/poa/cedulas/actividades/{activity_id}/seguimientos/3",
        json={
            "periodo_id": q3_period_id,
            "programado": 30,
            "alcanzado": 31,
            "progreso": "Se realizaron 31 eventos.",
            "alcance": "Cobertura institucional.",
        },
        headers=headers,
    )
    assert q3_follow_up.status_code == 200, q3_follow_up.text
    q3_evidence = await _attach_follow_up_file(
        client,
        headers,
        q3_follow_up.json()["id"],
        "tercer cuatrimestre",
        "2036-12-15",
    )
    assert q3_evidence.status_code == 201, q3_evidence.text
    q3_issue = await client.post(
        f"/api/v1/poa/cedulas/{form_id}/emisiones",
        json={"cuatrimestre": 3, "periodo_id": q3_period_id},
        headers=headers,
    )
    assert q3_issue.status_code == 201, q3_issue.text
    assert q3_issue.json()["nombre"] == ("Cédula Objetivo 6 - Septiembre-Diciembre 2036")
    assert Decimal(
        q3_issue.json()["snapshot"]["seccion_3_total_alcanzado"][0]["porcentaje_alcanzado"]
    ) == Decimal("120")
