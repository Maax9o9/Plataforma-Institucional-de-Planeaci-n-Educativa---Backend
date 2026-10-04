"""Borrado de piezas del POA durante su formulación.

Hasta ahora no existía ningún DELETE en el módulo: si Planeación agregaba una
cédula por error no había forma de quitarla. La regla que decidió el usuario
es simple pero exigente: se puede borrar sólo mientras el ejercicio siga en
borrador y antes de su fecha límite de formulación -la misma comprobación que
ya existía en `PoaExercise.ensure_editable`, declarada pero sin ningún caso de
uso que la invocara hasta esta tarea-. En cuanto Rectoría aprueba el
ejercicio, el POA es un compromiso institucional del que cuelgan informes,
evidencias y reportes: borrar entonces dejaría huecos en la historia.

Estas pruebas también verifican dos decisiones de diseño que no son sólo
código: qué pasa con los periodos que crean los cuatrimestres (se borran con
la cédula: no significan nada fuera de ella) y qué pasa si ya hay
seguimientos capturados o emisiones (bloquean el borrado, con la lectura más
restrictiva, aunque en teoría no deberían existir con el POA en borrador).
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest

from app.modules.identity_access.domain.value_objects import Role
from app.modules.poa_planning.domain.cedula_entities import PoaFormIssue
from test_ciclo_poa import _account
from test_poa_cedula_flow import _open_poa_period


async def _exercise(client, admin_headers, anio: int, *, with_deadline: bool = False) -> dict:
    # A diferencia de `test_ciclo_poa._new_exercise`, aquí el año es fijo y no
    # sale de un generador aleatorio compartido: cada prueba de este archivo
    # ya trae su propio año (ver los literales al pie del archivo), elegido
    # para no chocar con los años fijos que usan otras suites. Ir por un año
    # propio y determinista evita el mismo riesgo de colisión entre pruebas
    # que ya existe en el generador aleatorio.
    body = {"anio": anio}
    if with_deadline:
        body["fecha_limite_formulacion"] = f"{anio}-02-20"
    response = await client.post("/api/v1/poa/ejercicios", headers=admin_headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def _area(client, admin_headers, suffix: str) -> int:
    area = await client.post(
        "/api/v1/catalogos/areas",
        headers=admin_headers,
        json={"codigo": f"BORRA-{suffix}", "nombre": f"Área borrado POA {suffix}"},
    )
    assert area.status_code == 201, area.text
    return area.json()["id"]


async def _cedula_con_piezas(client, admin_headers, exercise_id: int, anio: int, area_id: int):
    """Cédula con un indicador y una actividad, lista para borrarse."""
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
    period_ids = {q["numero"]: q["periodo_id"] for q in form.json()["cuatrimestres"]}

    indicator = await client.post(
        f"/api/v1/poa/cedulas/{form_id}/indicadores",
        headers=admin_headers,
        json={"indicador_clave": "6.1.2", "numero_a_lograr": 100},
    )
    assert indicator.status_code == 201, indicator.text

    activity = await client.post(
        f"/api/v1/poa/cedulas/{form_id}/actividades",
        headers=admin_headers,
        json={
            "actividad_clave": "6.1.1",
            "unidad_medida": "Eventos",
            "meta_anual": 100,
            "area_ejecutora_id": area_id,
        },
    )
    assert activity.status_code == 201, activity.text

    return {
        "form_id": form_id,
        "indicator_id": indicator.json()["id"],
        "activity_id": activity.json()["id"],
        "period_ids": period_ids,
    }


async def _bitacora_acciones(client, admin_headers, entidad: str, entidad_id: int) -> list[str]:
    respuesta = await client.get(
        "/api/v1/bitacora",
        headers=admin_headers,
        params={"entidad": entidad, "entidad_id": entidad_id},
    )
    assert respuesta.status_code == 200, respuesta.text
    return [item["accion"] for item in respuesta.json()["items"]]


@pytest.mark.asyncio
async def test_borrar_cedula_en_borrador_se_lleva_indicadores_actividades_y_periodos(
    backend_client,
):
    app, client = backend_client
    suffix = uuid4().hex[:8]
    _, admin_headers = await _account(app, client, Role.ADMIN_SISTEMA, suffix)
    ejercicio = await _exercise(client, admin_headers, 2160)
    area_id = await _area(client, admin_headers, suffix)
    cedula = await _cedula_con_piezas(
        client, admin_headers, ejercicio["id"], ejercicio["anio"], area_id
    )

    borrado = await client.delete(
        f"/api/v1/poa/cedulas/{cedula['form_id']}", headers=admin_headers
    )
    assert borrado.status_code == 204, borrado.text

    # La cédula ya no existe.
    consulta = await client.get(
        f"/api/v1/poa/cedulas/{cedula['form_id']}", headers=admin_headers
    )
    assert consulta.status_code == 404, consulta.text

    # Se llevó consigo el indicador, la actividad y los tres cuatrimestres.
    repo = app.state.poa_form_repository
    assert await repo.get_form_indicator(cedula["indicator_id"]) is None
    assert await repo.get_form_activity(cedula["activity_id"]) is None
    assert await repo.list_form_quarters(cedula["form_id"]) == []

    # Los periodos que esos cuatrimestres habían creado tampoco significan
    # nada fuera de la cédula: se borran con ella en vez de quedar huérfanos.
    periods = app.state.period_repository
    for period_id in cedula["period_ids"].values():
        assert await periods.get_by_id(period_id) is None

    # Y queda registrado en la bitácora.
    acciones = await _bitacora_acciones(client, admin_headers, "poa_form", cedula["form_id"])
    assert "deleted" in acciones


@pytest.mark.asyncio
async def test_borrar_un_indicador_no_toca_el_resto_de_la_cedula(backend_client):
    app, client = backend_client
    suffix = uuid4().hex[:8]
    _, admin_headers = await _account(app, client, Role.ADMIN_SISTEMA, suffix)
    ejercicio = await _exercise(client, admin_headers, 2161)
    area_id = await _area(client, admin_headers, suffix)
    cedula = await _cedula_con_piezas(
        client, admin_headers, ejercicio["id"], ejercicio["anio"], area_id
    )

    borrado = await client.delete(
        f"/api/v1/poa/cedulas/indicadores/{cedula['indicator_id']}", headers=admin_headers
    )
    assert borrado.status_code == 204, borrado.text

    detalle = await client.get(
        f"/api/v1/poa/cedulas/{cedula['form_id']}", headers=admin_headers
    )
    assert detalle.status_code == 200, detalle.text
    assert detalle.json()["indicadores"] == []
    assert len(detalle.json()["actividades"]) == 1

    acciones = await _bitacora_acciones(
        client, admin_headers, "poa_form_indicator", cedula["indicator_id"]
    )
    assert "deleted" in acciones


@pytest.mark.asyncio
async def test_borrar_actividad_con_seguimiento_capturado_responde_conflicto(backend_client):
    """Prefiere la lectura restrictiva: en teoría no debería haber seguimientos
    con el POA en borrador -los informes llegan cuando ya está vigente-, pero
    la regla no se confía en esa teoría."""
    app, client = backend_client
    suffix = uuid4().hex[:8]
    _, admin_headers = await _account(app, client, Role.ADMIN_SISTEMA, suffix)
    ejercicio = await _exercise(client, admin_headers, 2162)
    area_id = await _area(client, admin_headers, suffix)
    cedula = await _cedula_con_piezas(
        client, admin_headers, ejercicio["id"], ejercicio["anio"], area_id
    )
    period_id = cedula["period_ids"][1]
    await _open_poa_period(client, admin_headers, period_id)

    seguimiento = await client.put(
        f"/api/v1/poa/cedulas/actividades/{cedula['activity_id']}/seguimientos/1",
        headers=admin_headers,
        json={"periodo_id": period_id, "programado": 40, "alcanzado": 10},
    )
    assert seguimiento.status_code == 200, seguimiento.text

    bloqueado = await client.delete(
        f"/api/v1/poa/cedulas/actividades/{cedula['activity_id']}", headers=admin_headers
    )
    assert bloqueado.status_code == 409, bloqueado.text
    assert bloqueado.json()["details"]["reason"] == "POA_ACTIVITY_HAS_FOLLOW_UPS"

    # Sigue intacta: el rechazo no tocó la actividad.
    detalle = await client.get(
        f"/api/v1/poa/cedulas/{cedula['form_id']}", headers=admin_headers
    )
    assert len(detalle.json()["actividades"]) == 1

    # Y por la misma razón la cédula completa tampoco puede borrarse.
    bloqueada_cedula = await client.delete(
        f"/api/v1/poa/cedulas/{cedula['form_id']}", headers=admin_headers
    )
    assert bloqueada_cedula.status_code == 409, bloqueada_cedula.text
    assert bloqueada_cedula.json()["details"]["reason"] == "POA_FORM_HAS_FOLLOW_UPS"


@pytest.mark.asyncio
async def test_borrar_cedula_con_emision_responde_conflicto_sin_romper_la_base(backend_client):
    """Una emisión (respaldo cuatrimestral) es un informe institucional: no
    puede desaparecer en silencio si la cédula se borra. En la práctica una
    emisión real siempre trae seguimientos completos (los exige `emitir`), así
    que esta prueba inserta la emisión directamente para ejercitar el segundo
    candado por sí solo -y, del lado de PostgreSQL, es también la comprobación
    de que `poa_cedula_emisiones` no tiene ON DELETE CASCADE: sin este candado
    de aplicación, el DELETE reventaría con un IntegrityError sin traducir.
    """
    app, client = backend_client
    suffix = uuid4().hex[:8]
    admin_user, admin_headers = await _account(app, client, Role.ADMIN_SISTEMA, suffix)
    ejercicio = await _exercise(client, admin_headers, 2163)
    area_id = await _area(client, admin_headers, suffix)
    cedula = await _cedula_con_piezas(
        client, admin_headers, ejercicio["id"], ejercicio["anio"], area_id
    )

    await app.state.poa_form_repository.add_issue(
        PoaFormIssue(
            form_id=cedula["form_id"],
            quarter=1,
            period_id=cedula["period_ids"][1],
            name="Emisión de prueba",
            snapshot={},
            issued_by=admin_user.id,
        )
    )

    bloqueado = await client.delete(
        f"/api/v1/poa/cedulas/{cedula['form_id']}", headers=admin_headers
    )
    assert bloqueado.status_code == 409, bloqueado.text
    assert bloqueado.json()["details"]["reason"] == "POA_FORM_HAS_ISSUES"

    consulta = await client.get(
        f"/api/v1/poa/cedulas/{cedula['form_id']}", headers=admin_headers
    )
    assert consulta.status_code == 200, consulta.text


@pytest.mark.asyncio
async def test_borrar_cedula_de_poa_aprobado_responde_error(backend_client):
    app, client = backend_client
    suffix = uuid4().hex[:8]
    _, admin_headers = await _account(app, client, Role.ADMIN_SISTEMA, suffix)
    _, rectoria_headers = await _account(app, client, Role.RECTORIA, suffix)
    ejercicio = await _exercise(client, admin_headers, 2164)
    area_id = await _area(client, admin_headers, suffix)
    cedula = await _cedula_con_piezas(
        client, admin_headers, ejercicio["id"], ejercicio["anio"], area_id
    )

    enviado = await client.post(
        f"/api/v1/poa/ejercicios/{ejercicio['id']}/enviar", headers=admin_headers
    )
    assert enviado.status_code == 200, enviado.text
    aprobado = await client.post(
        f"/api/v1/poa/ejercicios/{ejercicio['id']}/aprobar", headers=rectoria_headers
    )
    assert aprobado.status_code == 200, aprobado.text

    bloqueado = await client.delete(
        f"/api/v1/poa/cedulas/{cedula['form_id']}", headers=admin_headers
    )
    assert bloqueado.status_code == 422, bloqueado.text

    # La cédula sigue intacta: el ejercicio aprobado no permitió el borrado.
    consulta = await client.get(
        f"/api/v1/poa/cedulas/{cedula['form_id']}", headers=admin_headers
    )
    assert consulta.status_code == 200, consulta.text


@pytest.mark.asyncio
async def test_borrar_pasada_la_fecha_limite_de_formulacion_responde_error(
    backend_client, monkeypatch
):
    app, client = backend_client
    suffix = uuid4().hex[:8]
    _, admin_headers = await _account(app, client, Role.ADMIN_SISTEMA, suffix)
    ejercicio = await _exercise(client, admin_headers, 2165, with_deadline=True)
    anio = ejercicio["anio"]
    area_id = await _area(client, admin_headers, suffix)
    cedula = await _cedula_con_piezas(client, admin_headers, ejercicio["id"], anio, area_id)

    # La fecha límite (`fecha_limite_formulacion`) queda en {anio}-02-20; un
    # día después el ejercicio sigue en borrador pero ya no es editable.
    monkeypatch.setattr(
        "app.modules.poa_planning.application.use_cases.manage_cedula._today",
        lambda: date(anio, 2, 21),
    )

    bloqueado = await client.delete(
        f"/api/v1/poa/cedulas/indicadores/{cedula['indicator_id']}", headers=admin_headers
    )
    assert bloqueado.status_code == 422, bloqueado.text

    monkeypatch.undo()
    consulta = await client.get(
        f"/api/v1/poa/cedulas/{cedula['form_id']}", headers=admin_headers
    )
    assert consulta.status_code == 200, consulta.text
    assert len(consulta.json()["indicadores"]) == 1
