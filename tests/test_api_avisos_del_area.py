from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.modules.identity_access.domain.value_objects import Role
from app.modules.notifications.application.area_notices import (
    AVISO_DE_LA_APERTURA,
    AVISO_DE_PLANEACION,
    LARGO_DEL_MENSAJE,
    LARGO_DEL_TITULO,
    TITULO_DE_LA_APERTURA,
)
from app.modules.notifications.domain.entities import Notification
from app.modules.poa_institucional.infrastructure.sql_repository import (
    SqlAlchemyPoaAreaRepository,
)
from app.shared.domain.calendar import el_dia_en_letras, institutional_today
from helpers import API, anio_libre, crear_ejercicio, crear_poa

POA_INST = f"{API}/poa-institucional"
AVISOS = f"{API}/avisos"
NOTIFICACIONES = f"{API}/notificaciones"

HOY = institutional_today()
AYER = HOY - timedelta(days=1)
MANANA = HOY + timedelta(days=1)

LOS_CAMPOS_QUE_EL_FRONTEND_YA_LEE = {
    "id",
    "tipo",
    "mensaje",
    "entidad",
    "entidad_id",
    "leida",
    "enviada_por_correo",
    "fecha",
}

ROLES_QUE_REDACTAN_AVISOS = [
    Role.PLANEACION,
    Role.PLANEACION_ADMIN,
    Role.ADMIN_SISTEMA,
]

ROLES_QUE_NO_REDACTAN_AVISOS = [
    Role.CAPTURISTA_POA,
    Role.RESPONSABLE_AREA,
    Role.REVISOR_POA,
    Role.RECTORIA,
    Role.CONSULTA,
]


@pytest.fixture
async def ejercicio(backend_client, planeacion_headers) -> int:
    app, client = backend_client
    anio = await anio_libre(client, planeacion_headers)
    poa = await crear_poa(client, planeacion_headers, anio)
    creado = (await crear_ejercicio(client, planeacion_headers, poa, anio))["id"]
    if app.state.db_engine is None:
        yield creado
        return
    async with app.state.db_engine.connect() as conexion:
        transaccion = await conexion.begin()
        app.state.poa_area_repository = SqlAlchemyPoaAreaRepository(
            async_sessionmaker(
                bind=conexion, expire_on_commit=False, join_transaction_mode="create_savepoint"
            )
        )
        try:
            yield creado
        finally:
            await transaccion.rollback()


async def _abrir(client, cabeceras, ejercicio_id: int, *, areas, desde=AYER, hasta=MANANA):
    return await client.post(
        f"{POA_INST}/abrir",
        headers=cabeceras,
        params={"ejercicio_id": ejercicio_id},
        json={"areas": areas, "desde": desde.isoformat(), "hasta": hasta.isoformat()},
    )


async def _reabrir(client, cabeceras, ejercicio_id: int, area_id: int, *, desde, hasta):
    return await client.post(
        f"{POA_INST}/areas/{area_id}/reabrir",
        headers=cabeceras,
        params={"ejercicio_id": ejercicio_id},
        json={
            "desde": desde.isoformat(),
            "hasta": hasta.isoformat(),
            "motivo": "El área no entregó en la fecha dispuesta",
        },
    )


async def _redactar(client, cabeceras, *, areas, titulo="Un aviso", mensaje="El cuerpo del aviso."):
    return await client.post(
        AVISOS, headers=cabeceras, json={"areas": areas, "titulo": titulo, "mensaje": mensaje}
    )


async def _avisos_de(client, cabeceras, tipo: str | None = None) -> list[dict]:
    respuesta = await client.get(NOTIFICACIONES, headers=cabeceras)
    assert respuesta.status_code == 200, respuesta.text
    return [uno for uno in respuesta.json() if tipo is None or uno["tipo"] == tipo]


# ── El aviso que genera la apertura ──────────────────────────────────────────


async def test_la_apertura_avisa_a_cada_persona_del_area_con_las_dos_fechas(
    backend_client, planeacion_headers, ejercicio, nueva_area, cuenta_con_rol
):
    app, client = backend_client
    area = await nueva_area()
    nombre = (await app.state.area_repository.get_by_id(area)).name
    quien_captura = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=area)
    quien_encabeza = await cuenta_con_rol(Role.RESPONSABLE_AREA, area_id=area)

    abierto = await _abrir(client, planeacion_headers, ejercicio, areas=[area])

    assert abierto.status_code == 200, abierto.text
    for cabeceras in (quien_captura, quien_encabeza):
        avisos = await _avisos_de(client, cabeceras, AVISO_DE_LA_APERTURA)
        assert len(avisos) == 1
        assert avisos[0]["titulo"] == TITULO_DE_LA_APERTURA
        assert avisos[0]["mensaje"] == (
            "La Dirección de Planeación habilitó el registro de actividades del Programa "
            f"Operativo Anual del área de {nombre}. El periodo permanece abierto del "
            f"{el_dia_en_letras(AYER)} al {el_dia_en_letras(MANANA)}."
        )
        assert avisos[0]["leida"] is False


async def test_el_responsable_del_area_se_entera_de_que_su_propio_poa_se_abrio(
    backend_client, planeacion_headers, ejercicio, nueva_area, cuenta_con_rol
):
    _, client = backend_client
    area = await nueva_area()
    quien_encabeza = await cuenta_con_rol(Role.RESPONSABLE_AREA, area_id=area)

    await _abrir(client, planeacion_headers, ejercicio, areas=[area])

    assert len(await _avisos_de(client, quien_encabeza, AVISO_DE_LA_APERTURA)) == 1


@pytest.mark.parametrize("rol", [Role.CONSULTA, Role.REVISOR_POA, Role.RECTORIA])
async def test_quien_solo_consulta_el_area_no_recibe_el_aviso_de_la_apertura(
    backend_client, planeacion_headers, ejercicio, nueva_area, cuenta_con_rol, rol
):
    _, client = backend_client
    area = await nueva_area()
    quien_mira = await cuenta_con_rol(rol, area_id=area)

    await _abrir(client, planeacion_headers, ejercicio, areas=[area])

    assert await _avisos_de(client, quien_mira, AVISO_DE_LA_APERTURA) == []


async def test_el_aviso_de_la_apertura_de_un_area_no_llega_a_otra_area(
    backend_client, planeacion_headers, ejercicio, nueva_area, cuenta_con_rol
):
    _, client = backend_client
    area = await nueva_area()
    otra = await nueva_area()
    de_la_otra = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=otra)

    await _abrir(client, planeacion_headers, ejercicio, areas=[area])

    assert await _avisos_de(client, de_la_otra, AVISO_DE_LA_APERTURA) == []


async def test_abrir_dos_veces_lo_mismo_avisa_una_sola_vez(
    backend_client, planeacion_headers, ejercicio, nueva_area, cuenta_con_rol
):
    _, client = backend_client
    area = await nueva_area()
    quien_captura = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=area)

    primera = await _abrir(client, planeacion_headers, ejercicio, areas=[area])
    segunda = await _abrir(client, planeacion_headers, ejercicio, areas=[area])

    assert [uno["area_id"] for uno in primera.json()["abiertos"]] == [area]
    assert [uno["area_id"] for uno in segunda.json()["ya_estaban_abiertos"]] == [area]
    assert len(await _avisos_de(client, quien_captura, AVISO_DE_LA_APERTURA)) == 1


async def test_habilitar_un_periodo_nuevo_avisa_otra_vez_con_las_fechas_nuevas(
    backend_client, planeacion_headers, ejercicio, nueva_area, cuenta_con_rol
):
    _, client = backend_client
    area = await nueva_area()
    quien_captura = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=area)
    await _abrir(client, planeacion_headers, ejercicio, areas=[area])

    nuevo = await _reabrir(
        client,
        planeacion_headers,
        ejercicio,
        area,
        desde=date(2027, 1, 7),
        hasta=date(2027, 2, 1),
    )

    assert nuevo.status_code == 200, nuevo.text
    avisos = await _avisos_de(client, quien_captura, AVISO_DE_LA_APERTURA)
    assert len(avisos) == 2
    assert "del 7 de enero de 2027 al 1 de febrero de 2027" in avisos[0]["mensaje"]
    assert "habilitó un periodo nuevo" in avisos[0]["mensaje"]


async def test_abrir_para_todas_las_areas_avisa_en_cada_area_abierta(
    backend_client, planeacion_headers, ejercicio, nueva_area, cuenta_con_rol
):
    _, client = backend_client
    una = await nueva_area()
    otra = await nueva_area()
    de_una = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=una)
    de_otra = await cuenta_con_rol(Role.RESPONSABLE_AREA, area_id=otra)

    abierto = await _abrir(client, planeacion_headers, ejercicio, areas=None)

    assert abierto.status_code == 200, abierto.text
    assert len(await _avisos_de(client, de_una, AVISO_DE_LA_APERTURA)) == 1
    assert len(await _avisos_de(client, de_otra, AVISO_DE_LA_APERTURA)) == 1


async def test_la_apertura_dice_a_cuantas_personas_se_aviso_y_de_que_areas(
    backend_client, planeacion_headers, ejercicio, nueva_area, cuenta_con_rol
):
    _, client = backend_client
    una = await nueva_area()
    otra = await nueva_area()
    await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=una)
    await cuenta_con_rol(Role.RESPONSABLE_AREA, area_id=una)
    await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=otra)

    abierto = await _abrir(client, planeacion_headers, ejercicio, areas=[una, otra])

    assert abierto.status_code == 200, abierto.text
    cuerpo = abierto.json()
    assert cuerpo["avisados"] == 3
    assert {uno["area_id"]: uno["avisados"] for uno in cuerpo["abiertos"]} == {una: 2, otra: 1}
    assert cuerpo["areas_sin_a_quien_avisar"] == []

    # Lo que ya estaba abierto no se vuelve a avisar, y lo dice con un nulo y
    # no con un cero: un cero lo confundiria con un area sin nadie que capture.
    otra_vez = await _abrir(client, planeacion_headers, ejercicio, areas=[una, otra])

    assert otra_vez.json()["avisados"] == 0
    assert otra_vez.json()["areas_sin_a_quien_avisar"] == []
    assert [uno["avisados"] for uno in otra_vez.json()["ya_estaban_abiertos"]] == [None, None]


async def test_un_area_sin_quien_capture_se_reporta_y_no_se_silencia_al_abrir(
    backend_client, planeacion_headers, ejercicio, nueva_area, cuenta_con_rol
):
    _, client = backend_client
    con_gente = await nueva_area()
    vacia = await nueva_area()
    await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=con_gente)
    await cuenta_con_rol(Role.CONSULTA, area_id=vacia)

    abierto = await _abrir(client, planeacion_headers, ejercicio, areas=[con_gente, vacia])

    assert abierto.status_code == 200, abierto.text
    cuerpo = abierto.json()
    assert cuerpo["avisados"] == 1
    assert cuerpo["areas_sin_a_quien_avisar"] == [vacia]
    assert {uno["area_id"]: uno["avisados"] for uno in cuerpo["abiertos"]} == {
        con_gente: 1,
        vacia: 0,
    }


# ── El aviso que la Dirección de Planeación redacta ──────────────────────────


async def test_planeacion_redacta_un_aviso_y_llega_a_cada_persona_del_area(
    backend_client, planeacion_headers, nueva_area, cuenta_con_rol
):
    app, client = backend_client
    area = await nueva_area()
    nombre = (await app.state.area_repository.get_by_id(area)).name
    quien_captura = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=area)
    quien_encabeza = await cuenta_con_rol(Role.RESPONSABLE_AREA, area_id=area)

    redactado = await _redactar(
        client,
        planeacion_headers,
        areas=[area],
        titulo="Entrega del Programa Operativo Anual",
        mensaje="Las áreas entregan su Programa Operativo Anual antes del cierre del periodo.",
    )

    assert redactado.status_code == 200, redactado.text
    assert redactado.json() == {
        "entregados": 2,
        "areas": [{"area_id": area, "area": nombre, "personas": 2}],
    }
    for cabeceras in (quien_captura, quien_encabeza):
        avisos = await _avisos_de(client, cabeceras, AVISO_DE_PLANEACION)
        assert len(avisos) == 1
        assert avisos[0]["titulo"] == "Entrega del Programa Operativo Anual"
        assert avisos[0]["mensaje"] == (
            "Las áreas entregan su Programa Operativo Anual antes del cierre del periodo."
        )


async def test_un_area_sin_nadie_a_quien_avisar_se_reporta_y_no_se_silencia(
    backend_client, planeacion_headers, nueva_area, cuenta_con_rol
):
    app, client = backend_client
    con_gente = await nueva_area()
    vacia = await nueva_area()
    nombre_de_la_vacia = (await app.state.area_repository.get_by_id(vacia)).name
    await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=con_gente)
    await cuenta_con_rol(Role.CONSULTA, area_id=vacia)

    redactado = await _redactar(client, planeacion_headers, areas=[con_gente, vacia])

    assert redactado.status_code == 200, redactado.text
    cuerpo = redactado.json()
    assert cuerpo["entregados"] == 1
    assert {"area_id": vacia, "area": nombre_de_la_vacia, "personas": 0} in cuerpo["areas"]


async def test_el_aviso_para_todas_las_areas_se_dirige_con_un_nulo_explicito(
    backend_client, planeacion_headers, nueva_area, cuenta_con_rol
):
    _, client = backend_client
    una = await nueva_area()
    otra = await nueva_area()
    de_una = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=una)
    de_otra = await cuenta_con_rol(Role.RESPONSABLE_AREA, area_id=otra)

    redactado = await _redactar(client, planeacion_headers, areas=None)

    assert redactado.status_code == 200, redactado.text
    dirigidas = {uno["area_id"] for uno in redactado.json()["areas"]}
    assert {una, otra} <= dirigidas
    assert len(await _avisos_de(client, de_una, AVISO_DE_PLANEACION)) == 1
    assert len(await _avisos_de(client, de_otra, AVISO_DE_PLANEACION)) == 1


async def test_olvidar_las_areas_no_avisa_a_toda_la_universidad(
    backend_client, planeacion_headers, nueva_area, cuenta_con_rol
):
    _, client = backend_client
    area = await nueva_area()
    quien_captura = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=area)

    respuesta = await client.post(
        AVISOS,
        headers=planeacion_headers,
        json={"titulo": "Un aviso", "mensaje": "El cuerpo del aviso."},
    )

    assert respuesta.status_code == 422, respuesta.text
    assert await _avisos_de(client, quien_captura, AVISO_DE_PLANEACION) == []


async def test_una_lista_de_areas_vacia_se_rechaza_en_vez_de_avisar_a_todas(
    backend_client, planeacion_headers, nueva_area, cuenta_con_rol
):
    _, client = backend_client
    area = await nueva_area()
    quien_captura = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=area)

    respuesta = await _redactar(client, planeacion_headers, areas=[])

    assert respuesta.status_code == 422, respuesta.text
    assert await _avisos_de(client, quien_captura, AVISO_DE_PLANEACION) == []


async def test_un_aviso_dirigido_a_un_area_que_no_existe_se_rechaza(
    backend_client, planeacion_headers
):
    _, client = backend_client

    respuesta = await _redactar(client, planeacion_headers, areas=[10**8])

    assert respuesta.status_code == 422, respuesta.text


async def test_un_aviso_dirigido_a_un_area_retirada_se_rechaza_diciendo_cual(
    backend_client, planeacion_headers, nueva_area
):
    app, client = backend_client
    area_id = await nueva_area()
    area = await app.state.area_repository.get_by_id(area_id)
    area.is_active = False
    await app.state.area_repository.update(area)

    respuesta = await _redactar(client, planeacion_headers, areas=[area_id])

    assert respuesta.status_code == 422, respuesta.text
    assert area.name in respuesta.json()["message"]


@pytest.mark.parametrize("titulo", ["", "   "])
async def test_un_aviso_sin_titulo_se_rechaza(
    backend_client, planeacion_headers, nueva_area, titulo
):
    _, client = backend_client

    respuesta = await _redactar(
        client, planeacion_headers, areas=[await nueva_area()], titulo=titulo
    )

    assert respuesta.status_code == 422, respuesta.text


@pytest.mark.parametrize("mensaje", ["", "   "])
async def test_un_aviso_sin_mensaje_se_rechaza(
    backend_client, planeacion_headers, nueva_area, mensaje
):
    _, client = backend_client

    respuesta = await _redactar(
        client, planeacion_headers, areas=[await nueva_area()], mensaje=mensaje
    )

    assert respuesta.status_code == 422, respuesta.text


async def test_el_titulo_cabe_en_doscientos_caracteres_y_no_en_doscientos_uno(
    backend_client, planeacion_headers, nueva_area
):
    _, client = backend_client
    area = await nueva_area()

    cabe = await _redactar(client, planeacion_headers, areas=[area], titulo="t" * LARGO_DEL_TITULO)
    no_cabe = await _redactar(
        client, planeacion_headers, areas=[area], titulo="t" * (LARGO_DEL_TITULO + 1)
    )

    assert cabe.status_code == 200, cabe.text
    assert no_cabe.status_code == 422, no_cabe.text


async def test_el_mensaje_tiene_un_largo_maximo_declarado(
    backend_client, planeacion_headers, nueva_area
):
    _, client = backend_client
    area = await nueva_area()

    cabe = await _redactar(
        client, planeacion_headers, areas=[area], mensaje="m" * LARGO_DEL_MENSAJE
    )
    no_cabe = await _redactar(
        client, planeacion_headers, areas=[area], mensaje="m" * (LARGO_DEL_MENSAJE + 1)
    )

    assert cabe.status_code == 200, cabe.text
    assert no_cabe.status_code == 422, no_cabe.text


async def test_un_campo_que_el_aviso_no_declara_se_rechaza(
    backend_client, planeacion_headers, nueva_area
):
    _, client = backend_client

    respuesta = await client.post(
        AVISOS,
        headers=planeacion_headers,
        json={
            "areas": [await nueva_area()],
            "titulo": "Un aviso",
            "mensaje": "El cuerpo del aviso.",
            "tipo": AVISO_DE_LA_APERTURA,
        },
    )

    assert respuesta.status_code == 422, respuesta.text


# ── Quién puede redactar un aviso y quién no ─────────────────────────────────


@pytest.mark.parametrize("rol", ROLES_QUE_REDACTAN_AVISOS)
async def test_planeacion_y_el_administrador_del_sistema_redactan_avisos(
    backend_client, nueva_area, cuenta_con_rol, rol
):
    _, client = backend_client
    cabeceras = await cuenta_con_rol(rol, area_id=None)

    respuesta = await _redactar(client, cabeceras, areas=[await nueva_area()])

    assert respuesta.status_code == 200, respuesta.text


@pytest.mark.parametrize("rol", ROLES_QUE_NO_REDACTAN_AVISOS)
async def test_quien_no_es_planeacion_no_redacta_avisos(
    backend_client, nueva_area, cuenta_con_rol, rol
):
    _, client = backend_client
    area = await nueva_area()
    cabeceras = await cuenta_con_rol(rol, area_id=area)

    respuesta = await _redactar(client, cabeceras, areas=[area])

    assert respuesta.status_code == 403, respuesta.text


async def test_sin_sesion_no_se_redacta_ningun_aviso(backend_client, nueva_area):
    _, client = backend_client

    respuesta = await client.post(
        AVISOS,
        json={"areas": [await nueva_area()], "titulo": "Un aviso", "mensaje": "El cuerpo."},
    )

    assert respuesta.status_code == 401, respuesta.text


# ── Lo que `GET /notificaciones` devuelve ────────────────────────────────────


async def test_las_notificaciones_siguen_trayendo_lo_que_el_frontend_ya_leia(
    backend_client, planeacion_headers, nueva_area, cuenta_con_rol
):
    _, client = backend_client
    area = await nueva_area()
    quien_captura = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=area)
    await _redactar(client, planeacion_headers, areas=[area])

    avisos = await _avisos_de(client, quien_captura)

    assert len(avisos) == 1
    assert LOS_CAMPOS_QUE_EL_FRONTEND_YA_LEE < set(avisos[0])
    assert set(avisos[0]) == LOS_CAMPOS_QUE_EL_FRONTEND_YA_LEE | {"titulo"}


async def test_una_notificacion_sin_titulo_lo_devuelve_nulo_y_no_uno_inventado(
    backend_client, nueva_area, cuenta_con_rol
):
    app, client = backend_client
    area = await nueva_area()
    cabeceras = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=area)
    yo = next(uno for uno in await app.state.user_repository.list() if uno.area_id == area)

    await app.state.notification_repository.create(
        Notification(
            user_id=yo.id,
            notification_type="validacion",
            message="Su registro cambió de estado y requiere su atención.",
        )
    )

    avisos = await _avisos_de(client, cabeceras)

    assert [uno["titulo"] for uno in avisos] == [None]


async def test_un_aviso_marcado_como_leido_deja_de_estar_entre_los_no_leidos(
    backend_client, planeacion_headers, nueva_area, cuenta_con_rol
):
    _, client = backend_client
    area = await nueva_area()
    cabeceras = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=area)
    await _redactar(client, planeacion_headers, areas=[area])
    aviso = (await _avisos_de(client, cabeceras, AVISO_DE_PLANEACION))[0]

    leido = await client.post(f"{NOTIFICACIONES}/{aviso['id']}/leer", headers=cabeceras)

    assert leido.status_code == 204, leido.text
    sin_leer = await client.get(NOTIFICACIONES, headers=cabeceras, params={"no_leidas": True})
    assert sin_leer.json() == []


# ── El contrato del OpenAPI ──────────────────────────────────────────────────


async def test_el_aviso_declara_su_contrato_en_el_openapi(app):
    esquema = app.openapi()

    redactar = esquema["paths"][AVISOS]["post"]
    cuerpo = esquema["components"]["schemas"]["AvisoDePlaneacionRequest"]
    assert sorted(cuerpo["required"]) == ["areas", "mensaje", "titulo"]
    assert cuerpo["additionalProperties"] is False
    assert cuerpo["properties"]["titulo"]["maxLength"] == LARGO_DEL_TITULO
    assert cuerpo["properties"]["mensaje"]["maxLength"] == LARGO_DEL_MENSAJE

    respuesta = esquema["components"]["schemas"]["AvisoEntregadoRespuesta"]
    assert sorted(respuesta["required"]) == ["areas", "entregados"]
    por_area = esquema["components"]["schemas"]["AvisoPorAreaRespuesta"]
    assert sorted(por_area["required"]) == ["area", "area_id", "personas"]

    assert redactar["security"] != []
    assert {"401", "403", "422", "500", "503"} <= set(redactar["responses"])

    notificacion = esquema["components"]["schemas"]["NotificacionRespuesta"]
    assert sorted(notificacion["required"]) == sorted(
        LOS_CAMPOS_QUE_EL_FRONTEND_YA_LEE | {"titulo"}
    )
    assert notificacion["properties"]["titulo"]["anyOf"] == [
        {"maxLength": LARGO_DEL_TITULO, "type": "string"},
        {"type": "null"},
    ]


async def test_las_notificaciones_declaran_su_lista_en_el_openapi(app):
    esquema = app.openapi()

    consultar = esquema["paths"][NOTIFICACIONES]["get"]
    lista = consultar["responses"]["200"]["content"]["application/json"]["schema"]

    assert lista["type"] == "array"
    assert lista["items"]["$ref"].endswith("NotificacionRespuesta")
