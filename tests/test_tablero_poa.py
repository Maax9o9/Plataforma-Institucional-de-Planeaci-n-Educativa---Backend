"""Tablero del POA: criterio SEAES en la actividad y listado de seguimientos."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.modules.identity_access.domain.value_objects import Role
from test_ep08_revision_poa import _account, _capturar, _escenario
from test_poa_cedula_flow import _attach_follow_up_file


@pytest.mark.asyncio
async def test_el_area_asigna_el_criterio_seaes_de_su_actividad(backend_client):
    app, client = backend_client
    escenario = await _escenario(app, client)

    criterio = await client.post(
        "/api/v1/catalogos/criterios-seaes",
        headers=escenario["admin_headers"],
        json={"clave": f"C-{uuid4().hex[:6]}", "nombre": "Pertinencia de los programas"},
    )
    assert criterio.status_code == 201, criterio.text
    criterio_id = criterio.json()["id"]

    asignado = await client.patch(
        f"/api/v1/poa/cedulas/actividades/{escenario['activity_id']}/criterio-seaes",
        headers=escenario["capturer_headers"],
        json={"criterio_seaes_id": criterio_id},
    )

    assert asignado.status_code == 200, asignado.text
    assert asignado.json()["criterio_seaes_id"] == criterio_id


@pytest.mark.asyncio
async def test_el_criterio_debe_existir(backend_client):
    app, client = backend_client
    escenario = await _escenario(app, client)

    fallido = await client.patch(
        f"/api/v1/poa/cedulas/actividades/{escenario['activity_id']}/criterio-seaes",
        headers=escenario["capturer_headers"],
        json={"criterio_seaes_id": 999999},
    )

    assert fallido.status_code == 404, fallido.text


@pytest.mark.asyncio
async def test_el_listado_devuelve_la_tarjeta_completa(backend_client):
    app, client = backend_client
    escenario = await _escenario(app, client)
    seguimiento = await _capturar(client, escenario)
    await _attach_follow_up_file(
        client,
        escenario["capturer_headers"],
        seguimiento["id"],
        "tablero",
        escenario["cierre_q1"],
    )

    listado = await client.get(
        "/api/v1/poa/seguimientos",
        headers=escenario["capturer_headers"],
        params={"cuatrimestre": 1},
    )

    assert listado.status_code == 200, listado.text
    fila = next(x for x in listado.json()["items"] if x["id"] == seguimiento["id"])
    assert fila["estado"] == "borrador"
    assert fila["evidencias"] == 1
    assert fila["actividad"]["clave"] == "6.1.1"
    assert fila["actividad"]["unidad_medida"] == "Eventos"
    assert fila["programado"] == "40.0000"
    assert fila["criterio_seaes_id"] is None


@pytest.mark.asyncio
async def test_un_area_no_ve_los_seguimientos_de_otra(backend_client):
    app, client = backend_client
    primero = await _escenario(app, client)
    await _capturar(client, primero)
    segundo = await _escenario(app, client)
    ajeno = await _capturar(client, segundo)

    listado = await client.get(
        "/api/v1/poa/seguimientos",
        headers=primero["capturer_headers"],
        params={"area_id": segundo["area_id"]},
    )

    assert listado.status_code == 200, listado.text
    assert all(x["id"] != ajeno["id"] for x in listado.json()["items"])


@pytest.mark.asyncio
async def test_planeacion_ve_todas_las_areas_y_filtra_por_estado(backend_client):
    app, client = backend_client
    escenario = await _escenario(app, client)
    seguimiento = await _capturar(client, escenario)
    await _attach_follow_up_file(
        client,
        escenario["capturer_headers"],
        seguimiento["id"],
        "revision",
        escenario["cierre_q1"],
    )
    await client.post(
        f"/api/v1/poa/cedulas/seguimientos/{seguimiento['id']}/enviar",
        headers=escenario["capturer_headers"],
    )

    listado = await client.get(
        "/api/v1/poa/seguimientos",
        headers=escenario["planner_headers"],
        params={"estado": "enviado", "cuatrimestre": 1},
    )

    assert listado.status_code == 200, listado.text
    items = listado.json()["items"]
    assert any(x["id"] == seguimiento["id"] for x in items)
    assert {x["estado"] for x in items} == {"enviado"}


@pytest.mark.asyncio
async def test_area_sin_asignar_no_ve_nada(backend_client):
    """Un capturista sin área asignada no debe ver la lista completa: en el
    repositorio, `executing_area_id=None` significa "sin filtro", así que el
    endpoint debe reconocer este caso y devolver la página vacía sin consultar.
    """
    app, client = backend_client
    suffix = uuid4().hex[:8]
    _, sin_area_headers = await _account(app, client, Role.CAPTURISTA_POA, suffix)

    listado = await client.get(
        "/api/v1/poa/seguimientos",
        headers=sin_area_headers,
    )

    assert listado.status_code == 200, listado.text
    cuerpo = listado.json()
    assert cuerpo["items"] == []
    assert cuerpo["total"] == 0


@pytest.mark.asyncio
async def test_rectoria_ve_todas_las_areas_y_no_puede_escribir(backend_client):
    """Rectoría es de sólo lectura del tablero: ve cualquier área sin que el
    filtro se le fuerce, pero no puede enviar un seguimiento a revisión (una
    acción de escritura reservada a capturistas y planeación).
    """
    app, client = backend_client
    primero = await _escenario(app, client)
    propio = await _capturar(client, primero)
    segundo = await _escenario(app, client)
    ajeno = await _capturar(client, segundo)
    suffix = uuid4().hex[:8]
    _, rectoria_headers = await _account(app, client, Role.RECTORIA, suffix)

    listado_ajeno = await client.get(
        "/api/v1/poa/seguimientos",
        headers=rectoria_headers,
        params={"area_id": segundo["area_id"]},
    )

    assert listado_ajeno.status_code == 200, listado_ajeno.text
    assert any(x["id"] == ajeno["id"] for x in listado_ajeno.json()["items"])

    listado_propio = await client.get(
        "/api/v1/poa/seguimientos",
        headers=rectoria_headers,
        params={"area_id": primero["area_id"]},
    )

    assert listado_propio.status_code == 200, listado_propio.text
    assert any(x["id"] == propio["id"] for x in listado_propio.json()["items"])

    denegado = await client.post(
        f"/api/v1/poa/cedulas/seguimientos/{propio['id']}/enviar",
        headers=rectoria_headers,
    )

    assert denegado.status_code == 403, denegado.text
