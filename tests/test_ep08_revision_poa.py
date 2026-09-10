"""EP-08: ciclo de revisión del seguimiento cuatrimestral del POA.

El área captura su avance, lo envía a revisión y Planeación lo valida o lo
devuelve con un motivo. Antes de EP-08 el seguimiento se guardaba y nadie lo
aprobaba: la única acción posterior era la emisión, que es un respaldo
inmutable y no una validación.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.modules.identity_access.application.dto import RegisterUserCommand
from app.modules.identity_access.application.use_cases.create_user import CreateUser
from app.modules.identity_access.domain.value_objects import Role
from test_poa_cedula_flow import _attach_follow_up_file, _open_poa_period


async def _account(app, client, role: Role, suffix: str, area_id: int | None = None):
    email = f"ep08-{role.value}-{suffix}@example.com"
    user = await CreateUser(
        app.state.user_repository, app.state.password_hasher, app.state.event_bus
    ).execute(
        RegisterUserCommand(
            email=email,
            full_name=f"EP08 {role.value}",
            password="password-seguro",
            roles={role},
            area_id=area_id,
        )
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"correo": email, "contrasena": "password-seguro"},
    )
    assert login.status_code == 200, login.text
    return user, {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _ejercicio(client, headers, anio: int) -> int:
    creado = await client.post("/api/v1/poa/ejercicios", headers=headers, json={"anio": anio})
    if creado.status_code == 201:
        return creado.json()["id"]
    assert creado.status_code == 409, creado.text
    listado = await client.get("/api/v1/poa/ejercicios", headers=headers)
    assert listado.status_code == 200, listado.text
    items = listado.json()
    items = items["items"] if isinstance(items, dict) else items
    return next(item["id"] for item in items if item["anio"] == anio)


async def _escenario(app, client):
    """Cédula con una actividad, periodo abierto y un seguimiento en borrador."""
    suffix = uuid4().hex[:8]
    anio = 2199
    _, admin_headers = await _account(app, client, Role.ADMIN_SISTEMA, suffix)
    area = await client.post(
        "/api/v1/catalogos/areas",
        headers=admin_headers,
        json={"codigo": f"EP08-{suffix}", "nombre": f"Área ejecutora {suffix}"},
    )
    assert area.status_code == 201, area.text
    area_id = area.json()["id"]

    capturer, capturer_headers = await _account(
        app, client, Role.CAPTURISTA_POA, suffix, area_id
    )
    _, planner_headers = await _account(app, client, Role.PLANEACION, suffix)

    # La base de PostgreSQL persiste entre pruebas y el año del ejercicio es
    # único: el primer escenario lo crea y los siguientes lo reutilizan. Cada
    # uno trae su propia área, así que las cédulas no chocan entre sí.
    exercise_id = await _ejercicio(client, admin_headers, anio)
    form = await client.post(
        "/api/v1/poa/cedulas",
        headers=admin_headers,
        json={
            "ejercicio_id": exercise_id,
            "estrategia_clave": "6.1",
            "area_responsable_id": area_id,
            "cuatrimestres": [
                {"numero": 1, "fecha_inicio": f"{anio}-01-01", "fecha_fin": f"{anio}-04-30"},
                {"numero": 2, "fecha_inicio": f"{anio}-05-01", "fecha_fin": f"{anio}-08-31"},
                {"numero": 3, "fecha_inicio": f"{anio}-09-01", "fecha_fin": f"{anio}-12-31"},
            ],
        },
    )
    assert form.status_code == 201, form.text
    form_id = form.json()["id"]
    period_id = form.json()["cuatrimestres"][0]["periodo_id"]

    activity = await client.post(
        f"/api/v1/poa/cedulas/{form_id}/actividades",
        headers=admin_headers,
        json={
            "actividad_clave": "6.1.1",
            "area_ejecutora_id": area_id,
            "meta_anual": 100,
            "unidad_medida": "Eventos",
        },
    )
    assert activity.status_code == 201, activity.text
    activity_id = activity.json()["id"]

    await _open_poa_period(client, admin_headers, period_id)
    return {
        "admin_headers": admin_headers,
        "capturer": capturer,
        "capturer_headers": capturer_headers,
        "planner_headers": planner_headers,
        "activity_id": activity_id,
        "period_id": period_id,
        "area_id": area_id,
        "anio": anio,
        "cierre_q1": f"{anio}-04-30",
    }


async def _capturar(client, escenario, *, alcanzado=30, progreso="Avance del cuatrimestre"):
    body = {
        "periodo_id": escenario["period_id"],
        "programado": 40,
        "progreso": progreso,
        "alcance": "Comunidad universitaria",
    }
    if alcanzado is not None:
        body["alcanzado"] = alcanzado
    response = await client.put(
        f"/api/v1/poa/cedulas/actividades/{escenario['activity_id']}/seguimientos/1",
        headers=escenario["capturer_headers"],
        json=body,
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_seguimiento_nace_en_borrador(backend_client):
    app, client = backend_client
    escenario = await _escenario(app, client)

    seguimiento = await _capturar(client, escenario)

    assert seguimiento["estado"] == "borrador"
    assert seguimiento["comentario_revision"] is None


@pytest.mark.asyncio
async def test_no_se_envia_sin_evidencia(backend_client):
    app, client = backend_client
    escenario = await _escenario(app, client)
    seguimiento = await _capturar(client, escenario)

    rechazado = await client.post(
        f"/api/v1/poa/cedulas/seguimientos/{seguimiento['id']}/enviar",
        headers=escenario["capturer_headers"],
    )

    assert rechazado.status_code == 422, rechazado.text
    assert "evidencia" in rechazado.json()["message"].lower()


@pytest.mark.asyncio
async def test_no_se_envia_sin_valor_alcanzado(backend_client):
    app, client = backend_client
    escenario = await _escenario(app, client)
    seguimiento = await _capturar(client, escenario, alcanzado=None)
    await _attach_follow_up_file(
        client,
        escenario["capturer_headers"],
        seguimiento["id"],
        "sin-alcance",
        escenario["cierre_q1"],
    )

    rechazado = await client.post(
        f"/api/v1/poa/cedulas/seguimientos/{seguimiento['id']}/enviar",
        headers=escenario["capturer_headers"],
    )

    assert rechazado.status_code == 422, rechazado.text
    assert "alcanzado" in rechazado.json()["message"].lower()


@pytest.mark.asyncio
async def test_enviado_deja_de_ser_editable_por_el_area(backend_client):
    app, client = backend_client
    escenario = await _escenario(app, client)
    seguimiento = await _capturar(client, escenario)
    await _attach_follow_up_file(
        client,
        escenario["capturer_headers"],
        seguimiento["id"],
        "enviado",
        escenario["cierre_q1"],
    )

    enviado = await client.post(
        f"/api/v1/poa/cedulas/seguimientos/{seguimiento['id']}/enviar",
        headers=escenario["capturer_headers"],
    )
    assert enviado.status_code == 200, enviado.text
    assert enviado.json()["estado"] == "enviado"

    bloqueado = await client.put(
        f"/api/v1/poa/cedulas/actividades/{escenario['activity_id']}/seguimientos/1",
        headers=escenario["capturer_headers"],
        json={
            "periodo_id": escenario["period_id"],
            "programado": 40,
            "alcanzado": 999,
            "progreso": "Intento de cambio posterior al envío",
            "alcance": "Comunidad universitaria",
        },
    )
    assert bloqueado.status_code == 422, bloqueado.text
    assert bloqueado.json()["code"] == "INVALID_STATE"


@pytest.mark.asyncio
async def test_rechazo_devuelve_el_motivo_y_reabre_la_captura(backend_client):
    app, client = backend_client
    escenario = await _escenario(app, client)
    seguimiento = await _capturar(client, escenario)
    await _attach_follow_up_file(
        client,
        escenario["capturer_headers"],
        seguimiento["id"],
        "rechazo",
        escenario["cierre_q1"],
    )
    await client.post(
        f"/api/v1/poa/cedulas/seguimientos/{seguimiento['id']}/enviar",
        headers=escenario["capturer_headers"],
    )

    sin_motivo = await client.post(
        f"/api/v1/poa/cedulas/seguimientos/{seguimiento['id']}/rechazar",
        headers=escenario["planner_headers"],
        json={"comentario": "   "},
    )
    assert sin_motivo.status_code == 422, sin_motivo.text

    rechazado = await client.post(
        f"/api/v1/poa/cedulas/seguimientos/{seguimiento['id']}/rechazar",
        headers=escenario["planner_headers"],
        json={"comentario": "La evidencia no corresponde al cuatrimestre reportado."},
    )
    assert rechazado.status_code == 200, rechazado.text
    assert rechazado.json()["estado"] == "rechazado"
    assert "no corresponde" in rechazado.json()["comentario_revision"]

    # Rechazado vuelve a ser del área: puede corregir y reenviar.
    corregido = await _capturar(client, escenario, progreso="Corrección tras la devolución")
    assert corregido["estado"] == "rechazado"
    reenviado = await client.post(
        f"/api/v1/poa/cedulas/seguimientos/{seguimiento['id']}/enviar",
        headers=escenario["capturer_headers"],
    )
    assert reenviado.status_code == 200, reenviado.text
    assert reenviado.json()["estado"] == "enviado"
    assert reenviado.json()["comentario_revision"] is None


@pytest.mark.asyncio
async def test_el_area_no_puede_validar_su_propio_seguimiento(backend_client):
    app, client = backend_client
    escenario = await _escenario(app, client)
    seguimiento = await _capturar(client, escenario)
    await _attach_follow_up_file(
        client,
        escenario["capturer_headers"],
        seguimiento["id"],
        "autovalidacion",
        escenario["cierre_q1"],
    )
    await client.post(
        f"/api/v1/poa/cedulas/seguimientos/{seguimiento['id']}/enviar",
        headers=escenario["capturer_headers"],
    )

    denegado = await client.post(
        f"/api/v1/poa/cedulas/seguimientos/{seguimiento['id']}/validar",
        headers=escenario["capturer_headers"],
    )

    assert denegado.status_code == 403, denegado.text


@pytest.mark.asyncio
async def test_validado_queda_inmutable_y_con_historial_completo(backend_client):
    app, client = backend_client
    escenario = await _escenario(app, client)
    seguimiento = await _capturar(client, escenario)
    await _attach_follow_up_file(
        client,
        escenario["capturer_headers"],
        seguimiento["id"],
        "validado",
        escenario["cierre_q1"],
    )
    await client.post(
        f"/api/v1/poa/cedulas/seguimientos/{seguimiento['id']}/enviar",
        headers=escenario["capturer_headers"],
    )
    await client.post(
        f"/api/v1/poa/cedulas/seguimientos/{seguimiento['id']}/rechazar",
        headers=escenario["planner_headers"],
        json={"comentario": "Faltó desglosar el alcance."},
    )
    await client.post(
        f"/api/v1/poa/cedulas/seguimientos/{seguimiento['id']}/enviar",
        headers=escenario["capturer_headers"],
    )
    validado = await client.post(
        f"/api/v1/poa/cedulas/seguimientos/{seguimiento['id']}/validar",
        headers=escenario["planner_headers"],
    )
    assert validado.status_code == 200, validado.text
    assert validado.json()["estado"] == "validado"
    assert validado.json()["comentario_revision"] is None

    bloqueado = await client.put(
        f"/api/v1/poa/cedulas/actividades/{escenario['activity_id']}/seguimientos/1",
        headers=escenario["capturer_headers"],
        json={
            "periodo_id": escenario["period_id"],
            "programado": 40,
            "alcanzado": 999,
            "progreso": "Cambio después de validar",
            "alcance": "Comunidad universitaria",
        },
    )
    assert bloqueado.status_code == 422, bloqueado.text
    assert bloqueado.json()["code"] == "INVALID_STATE"

    historial = await client.get(
        f"/api/v1/poa/cedulas/seguimientos/{seguimiento['id']}/historial",
        headers=escenario["planner_headers"],
        params={"order": "asc"},
    )
    assert historial.status_code == 200, historial.text
    items = historial.json()["items"]
    assert [item["a_estado"] for item in items] == [
        "enviado",
        "rechazado",
        "enviado",
        "validado",
    ]
    assert items[1]["comentario"] == "Faltó desglosar el alcance."
    assert all(item["seguimiento_id"] == seguimiento["id"] for item in items)


@pytest.mark.asyncio
async def test_el_area_recibe_notificacion_del_dictamen(backend_client):
    app, client = backend_client
    escenario = await _escenario(app, client)
    seguimiento = await _capturar(client, escenario)
    await _attach_follow_up_file(
        client,
        escenario["capturer_headers"],
        seguimiento["id"],
        "aviso",
        escenario["cierre_q1"],
    )
    await client.post(
        f"/api/v1/poa/cedulas/seguimientos/{seguimiento['id']}/enviar",
        headers=escenario["capturer_headers"],
    )
    await client.post(
        f"/api/v1/poa/cedulas/seguimientos/{seguimiento['id']}/rechazar",
        headers=escenario["planner_headers"],
        json={"comentario": "Adjunta el acta de la reunión."},
    )

    avisos = await client.get(
        "/api/v1/notificaciones", headers=escenario["capturer_headers"]
    )
    assert avisos.status_code == 200, avisos.text
    cuerpo = avisos.json()
    items = cuerpo["items"] if isinstance(cuerpo, dict) else cuerpo
    devoluciones = [
        item
        for item in items
        if item["entidad"] == "poa_cedula_seguimiento"
        and item["entidad_id"] == seguimiento["id"]
    ]
    assert devoluciones, avisos.text
    assert "acta de la reunión" in devoluciones[0]["mensaje"]
