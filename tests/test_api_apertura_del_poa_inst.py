from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.modules.identity_access.domain.value_objects import Role
from app.modules.poa_institucional.api.schemas import PoaDelAreaRespuesta
from app.modules.poa_institucional.domain.entities import PoaArea
from app.modules.poa_institucional.infrastructure.sql_repository import (
    SqlAlchemyPoaAreaRepository,
)
from app.shared.domain.calendar import institutional_today
from helpers import API, anio_libre, crear_ejercicio, crear_poa

POA_INST = f"{API}/poa-institucional"

HOY = institutional_today()
AYER = HOY - timedelta(days=1)
MANANA = HOY + timedelta(days=1)


@pytest.fixture
async def ejercicio(backend_client, planeacion_headers) -> int:
    # Las filas de `poa_inst_areas` y `poa_inst_aperturas` se escriben sobre una
    # conexion con transaccion propia que se revierte al terminar, igual que en
    # `test_api_poa_del_area.py`. Sin eso quedan confirmadas en la copia de la
    # sesion, y la guarda del downgrade de la 0041 cuenta esas filas y se niega
    # a bajar la migracion: las pruebas de la migracion pasaban o fallaban segun
    # el orden alfabetico de los archivos.
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


async def _abrir(
    client,
    cabeceras: dict[str, str],
    ejercicio_id: int,
    *,
    areas: list[int] | None,
    desde: date = AYER,
    hasta: date = MANANA,
):
    return await client.post(
        f"{POA_INST}/abrir",
        headers=cabeceras,
        params={"ejercicio_id": ejercicio_id},
        json={
            "areas": areas,
            "desde": desde.isoformat(),
            "hasta": hasta.isoformat(),
        },
    )


async def _reabrir(
    client,
    cabeceras: dict[str, str],
    ejercicio_id: int,
    area_id: int,
    *,
    motivo: str = "El área no entregó en la fecha dispuesta",
    desde: date = AYER,
    hasta: date = MANANA,
    cuerpo: dict | None = None,
):
    return await client.post(
        f"{POA_INST}/areas/{area_id}/reabrir",
        headers=cabeceras,
        params={"ejercicio_id": ejercicio_id},
        json=cuerpo
        if cuerpo is not None
        else {"desde": desde.isoformat(), "hasta": hasta.isoformat(), "motivo": motivo},
    )


async def _consultar(client, cabeceras, ejercicio_id: int, area_id: int):
    return await client.get(
        f"{POA_INST}/areas/{area_id}",
        headers=cabeceras,
        params={"ejercicio_id": ejercicio_id},
    )


async def _registrar(client, cabeceras, ejercicio_id: int, area_id: int, denominacion: str):
    return await client.post(
        f"{POA_INST}/areas/{area_id}/actividades",
        headers=cabeceras,
        params={"ejercicio_id": ejercicio_id},
        json={"denominacion": denominacion},
    )


async def test_abrir_para_las_areas_elegidas_contesta_con_su_ventana(
    backend_client, planeacion_headers, ejercicio, nueva_area
):
    _, client = backend_client
    unas = sorted([await nueva_area(), await nueva_area()])

    abierto = await _abrir(client, planeacion_headers, ejercicio, areas=unas)

    assert abierto.status_code == 200, abierto.text
    cuerpo = abierto.json()
    assert cuerpo["ejercicio_id"] == ejercicio
    assert [uno["area_id"] for uno in cuerpo["abiertos"]] == unas
    assert cuerpo["ya_estaban_abiertos"] == []
    for uno in cuerpo["abiertos"]:
        assert uno["abierto_desde"] == AYER.isoformat()
        assert uno["abierto_hasta"] == MANANA.isoformat()
        assert uno["periodos_habilitados"] == 1
        assert uno["estado"] == "borrador"


async def test_abrir_para_todas_las_areas_no_se_escribe_con_una_lista(
    backend_client, planeacion_headers, ejercicio, nueva_area
):
    app, client = backend_client
    propia = await nueva_area()

    abierto = await _abrir(client, planeacion_headers, ejercicio, areas=None)

    assert abierto.status_code == 200, abierto.text
    activas = {area.id for area in await app.state.area_repository.list(active_only=True)}
    assert {uno["area_id"] for uno in abierto.json()["abiertos"]} == activas
    assert propia in activas


async def test_abrir_sin_decir_para_quien_se_rechaza_en_vez_de_abrir_para_todas(
    backend_client, planeacion_headers, ejercicio
):
    _, client = backend_client

    respuesta = await client.post(
        f"{POA_INST}/abrir",
        headers=planeacion_headers,
        params={"ejercicio_id": ejercicio},
        json={"desde": AYER.isoformat(), "hasta": MANANA.isoformat()},
    )

    assert respuesta.status_code == 422, respuesta.text


async def test_abrir_con_una_lista_vacia_se_rechaza(backend_client, planeacion_headers, ejercicio):
    _, client = backend_client

    respuesta = await _abrir(client, planeacion_headers, ejercicio, areas=[])

    assert respuesta.status_code == 422, respuesta.text


async def test_abrir_con_la_fecha_de_cierre_antes_de_la_de_apertura_se_rechaza(
    backend_client, planeacion_headers, ejercicio, nueva_area
):
    app, client = backend_client
    area = await nueva_area()

    respuesta = await _abrir(
        client, planeacion_headers, ejercicio, areas=[area], desde=MANANA, hasta=AYER
    )

    assert respuesta.status_code == 422, respuesta.text
    assert respuesta.json()["code"] == "BUSINESS_VALIDATION_ERROR"
    assert await app.state.poa_area_repository.find_poa_area(ejercicio, area) is None


async def test_el_poa_recien_abierto_dice_hasta_cuando_se_captura_y_que_esta_abierto(
    backend_client, planeacion_headers, ejercicio, nueva_area
):
    _, client = backend_client
    area = await nueva_area()
    await _abrir(client, planeacion_headers, ejercicio, areas=[area])

    leido = await _consultar(client, planeacion_headers, ejercicio, area)

    assert leido.status_code == 200, leido.text
    assert leido.json()["abierto_desde"] == AYER.isoformat()
    assert leido.json()["abierto_hasta"] == MANANA.isoformat()
    assert leido.json()["esta_abierto"] is True
    assert leido.json()["periodos_habilitados"] == 1


async def test_el_ultimo_dia_de_la_ventana_todavia_admite_capturar(
    backend_client, planeacion_headers, ejercicio, nueva_area
):
    _, client = backend_client
    area = await nueva_area()
    await _abrir(client, planeacion_headers, ejercicio, areas=[area], desde=HOY, hasta=HOY)

    registrada = await _registrar(
        client, planeacion_headers, ejercicio, area, "La que entró el último día"
    )

    assert registrada.status_code == 201, registrada.text
    leido = await _consultar(client, planeacion_headers, ejercicio, area)
    assert leido.json()["esta_abierto"] is True


async def test_pasada_la_fecha_de_cierre_registrar_se_bloquea_diciendo_la_fecha(
    backend_client, planeacion_headers, ejercicio, nueva_area
):
    app, client = backend_client
    area = await nueva_area()
    nombre = (await app.state.area_repository.get_by_id(area)).name
    await _abrir(
        client,
        planeacion_headers,
        ejercicio,
        areas=[area],
        desde=date(2026, 1, 1),
        hasta=date(2026, 1, 31),
    )

    bloqueada = await _registrar(client, planeacion_headers, ejercicio, area, "Fuera de plazo")

    assert bloqueada.status_code == 422, bloqueada.text
    assert bloqueada.json()["code"] == "INVALID_STATE"
    assert bloqueada.json()["message"] == (
        f"El periodo de captura del Programa Operativo Anual de {nombre} concluyó el "
        "31 de enero de 2026. Solicite a la Dirección de Planeación que habilite un nuevo "
        "periodo."
    )


async def test_antes_de_la_fecha_de_apertura_registrar_se_bloquea_diciendo_desde_cuando(
    backend_client, planeacion_headers, ejercicio, nueva_area
):
    _, client = backend_client
    area = await nueva_area()
    await _abrir(
        client,
        planeacion_headers,
        ejercicio,
        areas=[area],
        desde=date(2199, 3, 1),
        hasta=date(2199, 3, 31),
    )

    bloqueada = await _registrar(client, planeacion_headers, ejercicio, area, "Antes de tiempo")

    assert bloqueada.status_code == 422, bloqueada.text
    assert "inicia el 1 de marzo de 2199" in bloqueada.json()["message"]
    assert "a partir de esa fecha" in bloqueada.json()["message"]


async def test_un_poa_cerrado_se_sigue_consultando(
    backend_client, planeacion_headers, ejercicio, nueva_area, cuenta_con_rol
):
    _, client = backend_client
    area = await nueva_area()
    del_area = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=area)
    await _abrir(client, planeacion_headers, ejercicio, areas=[area], desde=HOY, hasta=HOY)
    registrada = await _registrar(client, planeacion_headers, ejercicio, area, "La que sí entró")
    assert registrada.status_code == 201, registrada.text
    await _reabrir(
        client,
        planeacion_headers,
        ejercicio,
        area,
        desde=date(2026, 1, 1),
        hasta=date(2026, 1, 31),
        motivo="Se cierra para dejarlo de consulta",
    )

    leido = await _consultar(client, del_area, ejercicio, area)

    assert leido.status_code == 200, leido.text
    assert leido.json()["esta_abierto"] is False
    assert [una["denominacion"] for una in leido.json()["actividades"]] == ["La que sí entró"]


async def test_reabrir_fija_un_periodo_nuevo_y_cuenta_cuantos_lleva(
    backend_client, planeacion_headers, ejercicio, nueva_area
):
    _, client = backend_client
    area = await nueva_area()
    await _abrir(
        client,
        planeacion_headers,
        ejercicio,
        areas=[area],
        desde=date(2026, 1, 1),
        hasta=date(2026, 1, 31),
    )

    reabierto = await _reabrir(client, planeacion_headers, ejercicio, area)

    assert reabierto.status_code == 200, reabierto.text
    assert reabierto.json()["abierto_desde"] == AYER.isoformat()
    assert reabierto.json()["abierto_hasta"] == MANANA.isoformat()
    assert reabierto.json()["esta_abierto"] is True
    assert reabierto.json()["periodos_habilitados"] == 2


async def test_tras_reabrir_el_area_vuelve_a_capturar(
    backend_client, planeacion_headers, ejercicio, nueva_area, cuenta_con_rol
):
    _, client = backend_client
    area = await nueva_area()
    del_area = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=area)
    await _abrir(
        client,
        planeacion_headers,
        ejercicio,
        areas=[area],
        desde=date(2026, 1, 1),
        hasta=date(2026, 1, 31),
    )
    bloqueada = await _registrar(client, del_area, ejercicio, area, "La que no cupo")
    assert bloqueada.status_code == 422, bloqueada.text

    await _reabrir(client, planeacion_headers, ejercicio, area)
    registrada = await _registrar(client, del_area, ejercicio, area, "La que ya cabe")

    assert registrada.status_code == 201, registrada.text


@pytest.mark.parametrize("motivo", ["", "   "])
async def test_reabrir_sin_decir_por_que_se_rechaza(
    backend_client, planeacion_headers, ejercicio, nueva_area, motivo
):
    _, client = backend_client
    area = await nueva_area()
    await _abrir(client, planeacion_headers, ejercicio, areas=[area])

    respuesta = await _reabrir(client, planeacion_headers, ejercicio, area, motivo=motivo)

    assert respuesta.status_code == 422, respuesta.text


async def test_reabrir_sin_mandar_el_motivo_se_rechaza(
    backend_client, planeacion_headers, ejercicio, nueva_area
):
    _, client = backend_client
    area = await nueva_area()
    await _abrir(client, planeacion_headers, ejercicio, areas=[area])

    respuesta = await _reabrir(
        client,
        planeacion_headers,
        ejercicio,
        area,
        cuerpo={"desde": AYER.isoformat(), "hasta": MANANA.isoformat()},
    )

    assert respuesta.status_code == 422, respuesta.text


async def test_reabrir_lo_que_nadie_abrio_contesta_404_diciendo_que_lo_abra(
    backend_client, planeacion_headers, ejercicio, nueva_area
):
    app, client = backend_client
    area = await nueva_area()
    nombre = (await app.state.area_repository.get_by_id(area)).name

    respuesta = await _reabrir(client, planeacion_headers, ejercicio, area)

    assert respuesta.status_code == 404, respuesta.text
    assert respuesta.json()["code"] == "RESOURCE_NOT_FOUND"
    assert respuesta.json()["message"] == (
        f"El área de {nombre} no tiene un Programa Operativo Anual abierto en este ejercicio. "
        "Ábralo antes de habilitar un nuevo periodo de captura."
    )


#: Los cinco dias de un periodo de tres, de fuera a fuera. Un `<` donde va
#: `<=` se cae en el primero y un `>` donde va `>=` en el ultimo, y los tres
#: dias de en medio no los salvan. Van en una sola prueba, con un solo
#: ejercicio, porque `poa_ejercicios.anio` es unico en todo el sistema y la
#: suite esta a pocos anios libres de su techo: cada prueba de este archivo
#: que pida la fixture `ejercicio` gasta uno.
LOS_CINCO_DIAS_DEL_PERIODO = (
    (-1, "por_iniciar", None),
    (0, "abierto", 2),
    (1, "abierto", 1),
    (2, "abierto", 0),
    (3, "concluido", None),
)


async def test_el_registro_dice_su_motivo_y_sus_dias_en_los_dos_bordes_y_fuera(
    backend_client, planeacion_headers, ejercicio, nueva_area, monkeypatch
):
    _, client = backend_client
    area = await nueva_area()
    primero = HOY
    ultimo = HOY + timedelta(days=2)
    await _abrir(client, planeacion_headers, ejercicio, areas=[area], desde=primero, hasta=ultimo)

    medido = []
    for desplazamiento, _, _ in LOS_CINCO_DIAS_DEL_PERIODO:
        monkeypatch.setattr(
            "app.modules.poa_institucional.api.router.institutional_today",
            lambda dia=primero + timedelta(days=desplazamiento): dia,
        )
        leido = await _consultar(client, planeacion_headers, ejercicio, area)
        assert leido.status_code == 200, leido.text
        cuerpo = leido.json()
        medido.append((desplazamiento, cuerpo["estado_del_registro"], cuerpo["dias_restantes"]))
        assert cuerpo["esta_abierto"] is (cuerpo["estado_del_registro"] == "abierto")

    assert medido == list(LOS_CINCO_DIAS_DEL_PERIODO)


def test_un_poa_sin_ningun_periodo_dice_que_nunca_se_habilito():
    sin_periodo = PoaDelAreaRespuesta.from_domain(
        PoaArea(id=1, exercise_id=7, area_id=11),
        [],
        falta_para_presentar=[],
        ventana=None,
        hoy=HOY,
    )

    assert sin_periodo.esta_abierto is False
    assert sin_periodo.estado_del_registro.value == "sin_habilitar"
    assert sin_periodo.dias_restantes is None


async def test_la_apertura_declara_su_contrato_en_el_openapi(app):
    esquema = app.openapi()

    abrir = esquema["paths"][f"{POA_INST}/abrir"]["post"]
    reabrir = esquema["paths"][f"{POA_INST}/areas/{{area_id}}/reabrir"]["post"]

    cuerpo_de_abrir = esquema["components"]["schemas"]["AbrirElPoaRequest"]
    assert sorted(cuerpo_de_abrir["required"]) == ["areas", "desde", "hasta"]
    cuerpo_de_reabrir = esquema["components"]["schemas"]["ReabrirElPoaRequest"]
    assert sorted(cuerpo_de_reabrir["required"]) == ["desde", "hasta", "motivo"]

    respuesta = esquema["components"]["schemas"]["AperturaDelPoaRespuesta"]
    assert sorted(respuesta["required"]) == [
        "abiertos",
        "areas_sin_a_quien_avisar",
        "avisados",
        "ejercicio_id",
        "ya_estaban_abiertos",
    ]
    por_area = esquema["components"]["schemas"]["PoaDelAreaAbiertoRespuesta"]
    assert "avisados" in por_area["required"]
    del_area = esquema["components"]["schemas"]["PoaDelAreaRespuesta"]
    assert {
        "abierto_desde",
        "abierto_hasta",
        "dias_restantes",
        "esta_abierto",
        "estado_del_registro",
        "periodos_habilitados",
    } <= set(del_area["properties"])
    assert {"dias_restantes", "estado_del_registro"} <= set(del_area["required"])
    motivos = esquema["components"]["schemas"]["EstadoDelRegistro"]
    assert sorted(motivos["enum"]) == ["abierto", "concluido", "por_iniciar", "sin_habilitar"]

    for nombre, operacion in (("abrir", abrir), ("reabrir", reabrir)):
        obligatorios = {
            parametro["name"]
            for parametro in operacion["parameters"]
            if parametro["required"] and parametro["in"] == "query"
        }
        assert obligatorios == {"ejercicio_id"}, nombre
        assert operacion["security"] != [], nombre
        assert {"401", "403", "409", "422", "500", "503"} <= set(operacion["responses"]), nombre
    assert "404" in reabrir["responses"]
    assert "404" not in abrir["responses"]


async def test_la_respuesta_calcula_si_esta_abierto_con_el_calendario_institucional(
    backend_client, planeacion_headers, ejercicio, nueva_area, monkeypatch
):
    # El dia lo decide el calendario de America/Mexico_City y no el reloj del
    # servidor: con `date.today` en un servidor en UTC, la tarde del ultimo dia
    # de la ventana en Chiapas ya seria el dia siguiente y la respuesta diria
    # que el periodo cerro un dia antes.
    _, client = backend_client
    area = await nueva_area()
    await _abrir(client, planeacion_headers, ejercicio, areas=[area], desde=HOY, hasta=HOY)
    monkeypatch.setattr(
        "app.modules.poa_institucional.api.router.institutional_today",
        lambda: HOY + timedelta(days=1),
    )

    leido = await _consultar(client, planeacion_headers, ejercicio, area)

    assert leido.status_code == 200, leido.text
    assert leido.json()["esta_abierto"] is False
