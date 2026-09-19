"""Tablero del POA: criterio SEAES en la actividad y listado de seguimientos."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from app.modules.identity_access.domain.value_objects import Role
from test_ep08_revision_poa import _account, _capturar, _escenario
from test_poa_cedula_flow import _attach_follow_up_file


@pytest.mark.asyncio
async def test_la_ruta_singular_de_criterio_fue_retirada(backend_client):
    """SEAES admite varios criterios por actividad desde la migración 0031:
    la ruta vieja en singular ya no puede representar el dato y responde 410
    señalando la ruta plural, en vez de fallar en silencio con un 404.
    """
    app, client = backend_client
    escenario = await _escenario(app, client)

    retirada = await client.patch(
        f"/api/v1/poa/cedulas/actividades/{escenario['activity_id']}/criterio-seaes",
        headers=escenario["capturer_headers"],
        json={"criterio_seaes_id": 1},
    )

    assert retirada.status_code == 410, retirada.text
    assert "criterios-seaes" in retirada.json()["message"]


@pytest.mark.asyncio
async def test_el_area_asigna_los_criterios_seaes_de_su_actividad(backend_client):
    app, client = backend_client
    escenario = await _escenario(app, client)

    criterio_uno = await client.post(
        "/api/v1/catalogos/criterios-seaes",
        headers=escenario["admin_headers"],
        json={"clave": f"C-{uuid4().hex[:6]}", "nombre": "Pertinencia de los programas"},
    )
    assert criterio_uno.status_code == 201, criterio_uno.text
    criterio_dos = await client.post(
        "/api/v1/catalogos/criterios-seaes",
        headers=escenario["admin_headers"],
        json={"clave": f"C-{uuid4().hex[:6]}", "nombre": "Cobertura y equidad"},
    )
    assert criterio_dos.status_code == 201, criterio_dos.text
    id_uno, id_dos = criterio_uno.json()["id"], criterio_dos.json()["id"]

    asignado = await client.patch(
        f"/api/v1/poa/cedulas/actividades/{escenario['activity_id']}/criterios-seaes",
        headers=escenario["capturer_headers"],
        json={"criterio_seaes_ids": [max(id_uno, id_dos), min(id_uno, id_dos)]},
    )

    assert asignado.status_code == 200, asignado.text
    assert asignado.json()["criterio_seaes_ids"] == sorted([id_uno, id_dos])


@pytest.mark.asyncio
async def test_asignar_el_criterio_deja_bitacora_y_mueve_la_marca_de_tiempo(backend_client):
    """La cobertura SEAES es lo que mide el semáforo institucional: quién la
    asignó y cuándo tiene que quedar auditado. La marca de tiempo se compara
    contra la que dejó el alta de la actividad, así que la prueba falla si la
    asignación vuelve a saltarse la capa de casos de uso.
    """
    app, client = backend_client
    escenario = await _escenario(app, client)
    repositorio = app.state.poa_form_repository
    antes = (await repositorio.get_form_activity(escenario["activity_id"])).updated_at

    criterio = await client.post(
        "/api/v1/catalogos/criterios-seaes",
        headers=escenario["admin_headers"],
        json={"clave": f"C-{uuid4().hex[:6]}", "nombre": "Cobertura y equidad"},
    )
    assert criterio.status_code == 201, criterio.text

    asignado = await client.patch(
        f"/api/v1/poa/cedulas/actividades/{escenario['activity_id']}/criterios-seaes",
        headers=escenario["capturer_headers"],
        json={"criterio_seaes_ids": [criterio.json()["id"]]},
    )
    assert asignado.status_code == 200, asignado.text

    bitacora = await client.get(
        "/api/v1/bitacora",
        headers=escenario["admin_headers"],
        params={"entidad": "poa_form_activity", "entidad_id": escenario["activity_id"]},
    )
    assert bitacora.status_code == 200, bitacora.text
    acciones = [item["accion"] for item in bitacora.json()["items"]]
    assert "criteria_assigned" in acciones, bitacora.text

    despues = (await repositorio.get_form_activity(escenario["activity_id"])).updated_at
    assert despues > antes, (antes, despues)


@pytest.mark.asyncio
async def test_el_criterio_debe_existir(backend_client):
    app, client = backend_client
    escenario = await _escenario(app, client)

    fallido = await client.patch(
        f"/api/v1/poa/cedulas/actividades/{escenario['activity_id']}/criterios-seaes",
        headers=escenario["capturer_headers"],
        json={"criterio_seaes_ids": [999999]},
    )

    assert fallido.status_code == 404, fallido.text
    assert "999999" in fallido.json()["message"]


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
    assert Decimal(fila["programado"]) == Decimal("40")
    assert fila["criterio_seaes_ids"] == []


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

    El escenario ajeno se monta aquí mismo, con su propia área y su propio
    seguimiento, para que la prueba no dependa de datos que hayan dejado otras
    pruebas: así falla si se quita el centinela, sea cual sea la variante o el
    orden de ejecución.
    """
    app, client = backend_client
    ajeno = await _escenario(app, client)
    await _capturar(client, ajeno)
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
async def test_un_capturista_no_lee_el_historial_de_otra_area(backend_client):
    """El historial trae los comentarios de revisión: son datos del área. Un
    capturista de otra área que conozca el id del seguimiento debe recibir 403,
    y el dueño debe seguir leyendo el suyo — si no, la comprobación sería un
    portazo indiscriminado en vez de un filtro por área.
    """
    app, client = backend_client
    ajeno = await _escenario(app, client)
    seguimiento = await _capturar(client, ajeno)
    await _attach_follow_up_file(
        client,
        ajeno["capturer_headers"],
        seguimiento["id"],
        "historial",
        ajeno["cierre_q1"],
    )
    await client.post(
        f"/api/v1/poa/cedulas/seguimientos/{seguimiento['id']}/enviar",
        headers=ajeno["capturer_headers"],
    )
    await client.post(
        f"/api/v1/poa/cedulas/seguimientos/{seguimiento['id']}/rechazar",
        headers=ajeno["planner_headers"],
        json={"comentario": "El acta no corresponde al cuatrimestre."},
    )
    intruso = await _escenario(app, client)

    denegado = await client.get(
        f"/api/v1/poa/cedulas/seguimientos/{seguimiento['id']}/historial",
        headers=intruso["capturer_headers"],
    )

    assert denegado.status_code == 403, denegado.text

    propio = await client.get(
        f"/api/v1/poa/cedulas/seguimientos/{seguimiento['id']}/historial",
        headers=ajeno["capturer_headers"],
    )

    assert propio.status_code == 200, propio.text
    comentarios = [item["comentario"] for item in propio.json()["items"]]
    assert "El acta no corresponde al cuatrimestre." in comentarios


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


@pytest.mark.asyncio
async def test_la_tarjeta_trae_lo_que_el_area_escribio_no_solo_los_numeros(backend_client):
    """El área captura su avance desde la tarjeta del tablero, y el PUT que lo
    guarda reemplaza el seguimiento completo. Si la tarjeta no devolviera la
    justificación, el progreso y el alcance, el formulario abriría en blanco y
    la siguiente corrección —cambiar un número, por ejemplo— borraría el texto
    que el área ya había escrito, sin avisar.
    """
    app, client = backend_client
    escenario = await _escenario(app, client)
    seguimiento = await _capturar(client, escenario, alcanzado=30)
    corregido = await client.put(
        f"/api/v1/poa/cedulas/actividades/{escenario['activity_id']}/seguimientos/1",
        headers=escenario["capturer_headers"],
        json={
            "periodo_id": escenario["period_id"],
            "programado": 40,
            "alcanzado": 30,
            "justificacion_desviacion": "Dos eventos se recorrieron al segundo cuatrimestre.",
            "progreso": "Se realizaron 30 de los 40 eventos programados.",
            "alcance": "Comunidad universitaria",
        },
    )
    assert corregido.status_code == 200, corregido.text

    listado = await client.get(
        "/api/v1/poa/seguimientos",
        headers=escenario["capturer_headers"],
        params={"cuatrimestre": 1},
    )

    assert listado.status_code == 200, listado.text
    fila = next(x for x in listado.json()["items"] if x["id"] == seguimiento["id"])
    assert fila["justificacion_desviacion"] == (
        "Dos eventos se recorrieron al segundo cuatrimestre."
    )
    assert fila["progreso"] == "Se realizaron 30 de los 40 eventos programados."
    assert fila["alcance"] == "Comunidad universitaria"


@pytest.mark.asyncio
async def test_se_puede_pedir_un_seguimiento_por_su_id(backend_client):
    """La captura del avance es una pantalla propia con su URL, así que tiene
    que poder cargarse sola: recargar el navegador o pegar el enlace no puede
    depender de haber pasado antes por el tablero.
    """
    app, client = backend_client
    escenario = await _escenario(app, client)
    seguimiento = await _capturar(client, escenario)

    respuesta = await client.get(
        f"/api/v1/poa/seguimientos/{seguimiento['id']}",
        headers=escenario["capturer_headers"],
    )

    assert respuesta.status_code == 200, respuesta.text
    fila = respuesta.json()
    assert fila["id"] == seguimiento["id"]
    assert fila["actividad"]["clave"] == "6.1.1"
    assert fila["actividad"]["unidad_medida"] == "Eventos"
    assert Decimal(fila["programado"]) == Decimal("40")
    assert fila["progreso"] == "Avance del cuatrimestre"


@pytest.mark.asyncio
async def test_un_area_no_puede_abrir_el_seguimiento_de_otra(backend_client):
    """Mismo candado que el listado: la URL de la pantalla es adivinable
    cambiando un número, así que el permiso se comprueba aquí y no en el
    filtro del tablero.
    """
    app, client = backend_client
    primero = await _escenario(app, client)
    segundo = await _escenario(app, client)
    ajeno = await _capturar(client, segundo)

    respuesta = await client.get(
        f"/api/v1/poa/seguimientos/{ajeno['id']}",
        headers=primero["capturer_headers"],
    )

    assert respuesta.status_code == 403, respuesta.text


@pytest.mark.asyncio
async def test_planeacion_si_puede_abrir_el_seguimiento_de_cualquier_area(backend_client):
    app, client = backend_client
    escenario = await _escenario(app, client)
    seguimiento = await _capturar(client, escenario)

    respuesta = await client.get(
        f"/api/v1/poa/seguimientos/{seguimiento['id']}",
        headers=escenario["planner_headers"],
    )

    assert respuesta.status_code == 200, respuesta.text


@pytest.mark.asyncio
async def test_pedir_un_seguimiento_inexistente_responde_404(backend_client):
    app, client = backend_client
    escenario = await _escenario(app, client)

    respuesta = await client.get(
        "/api/v1/poa/seguimientos/999999",
        headers=escenario["planner_headers"],
    )

    assert respuesta.status_code == 404, respuesta.text
