from __future__ import annotations

import os

import asyncpg
import pytest
from sqlalchemy import text

from conftest import devolver_los_anios_al_pozo
from helpers import (
    API,
    SE_ACABARON_LOS_ANIOS,
    ULTIMO_ANIO_DEL_CONTRATO,
    anio_libre,
    crear_ejercicio,
    crear_ejercicio_de_un_anio_libre,
    crear_poa,
    cuatrimestres,
    poa_inicial_id,
    primer_anio_por_venir,
)


def _solo_en_postgresql(app):
    if app.state.db_engine is None:
        pytest.skip("El pozo de años es el de PostgreSQL; el de memoria es de cada aplicación.")
    return app.state.db_engine


async def _anios_tomados(motor) -> set[int]:
    async with motor.connect() as conexion:
        filas = await conexion.execute(text("SELECT anio FROM poa_ejercicios"))
        return {fila.anio for fila in filas}


async def _ejercicios_en_la_base_de_pruebas() -> int:
    dsn = os.environ["TEST_DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    conexion = await asyncpg.connect(dsn)
    try:
        return await conexion.fetchval("SELECT count(*) FROM poa_ejercicios")
    finally:
        await conexion.close()


async def test_el_pozo_devuelve_el_anio_del_ejercicio_que_no_sostiene_nada(
    backend_client, planeacion_headers
):
    app, client = backend_client
    motor = _solo_en_postgresql(app)

    catalogo_id = await poa_inicial_id(client, planeacion_headers)
    ejercicio = await crear_ejercicio_de_un_anio_libre(client, planeacion_headers, catalogo_id)
    anio = ejercicio["anio"]
    assert anio in await _anios_tomados(motor)

    devueltos = await devolver_los_anios_al_pozo(motor, {anio})

    assert devueltos == {anio}
    assert anio not in await _anios_tomados(motor)
    assert await anio_libre(client, planeacion_headers, desde=anio) == anio


async def test_el_pozo_no_devuelve_el_anio_del_ejercicio_que_sostiene_una_cedula(
    backend_client, planeacion_headers, area_propia
):
    app, client = backend_client
    motor = _solo_en_postgresql(app)

    catalogo_id = await poa_inicial_id(client, planeacion_headers)
    ejercicio = await crear_ejercicio_de_un_anio_libre(client, planeacion_headers, catalogo_id)
    anio = ejercicio["anio"]
    cedula = await client.post(
        f"{API}/poa/cedulas",
        headers=planeacion_headers,
        json={
            "ejercicio_id": ejercicio["id"],
            "estrategia_clave": "1.1",
            "area_responsable_id": area_propia,
            "cuatrimestres": cuatrimestres(anio),
        },
    )
    assert cedula.status_code == 201, cedula.text

    devueltos = await devolver_los_anios_al_pozo(motor, {anio})

    assert devueltos == set()
    assert anio in await _anios_tomados(motor)


async def test_lo_que_el_pozo_no_presto_no_lo_borra(backend_client, planeacion_headers):
    app, client = backend_client
    motor = _solo_en_postgresql(app)

    catalogo_id = await poa_inicial_id(client, planeacion_headers)
    ajeno = await crear_ejercicio_de_un_anio_libre(client, planeacion_headers, catalogo_id)

    devueltos = await devolver_los_anios_al_pozo(motor, set())

    assert devueltos == set()
    assert ajeno["anio"] in await _anios_tomados(motor)


async def test_cuando_se_acaban_los_anios_de_ejercicio_el_fallo_lo_dice(
    backend_client, planeacion_headers
):
    app, client = backend_client
    motor = _solo_en_postgresql(app)

    tomados = {
        ejercicio["anio"]
        for ejercicio in (
            await client.get(f"{API}/poa/ejercicios", headers=planeacion_headers)
        ).json()
    }
    assert ULTIMO_ANIO_DEL_CONTRATO not in tomados, (
        f"Esta prueba necesita el {ULTIMO_ANIO_DEL_CONTRATO} libre para agotar una ventana "
        f"del pozo sin agotarlo entero. Hay {len(tomados)} años tomados."
    )
    poa = await crear_poa(client, planeacion_headers, ULTIMO_ANIO_DEL_CONTRATO)
    await crear_ejercicio(client, planeacion_headers, poa, ULTIMO_ANIO_DEL_CONTRATO)

    with pytest.raises(pytest.fail.Exception, match=SE_ACABARON_LOS_ANIOS):
        await anio_libre(client, planeacion_headers, desde=ULTIMO_ANIO_DEL_CONTRATO)

    assert await devolver_los_anios_al_pozo(motor, {ULTIMO_ANIO_DEL_CONTRATO}) == {
        ULTIMO_ANIO_DEL_CONTRATO
    }


async def test_el_ayudante_de_la_migracion_tambien_dice_que_se_acabaron(backend_client):
    from test_apertura_del_poa_inst_migracion import _anio_libre

    app, _ = backend_client
    motor = _solo_en_postgresql(app)

    async with motor.connect() as conexion:
        with pytest.raises(pytest.fail.Exception, match=SE_ACABARON_LOS_ANIOS):
            await _anio_libre(conexion, ULTIMO_ANIO_DEL_CONTRATO + 1)


async def test_la_variante_de_memoria_no_consume_del_pozo_de_postgresql(
    backend_client, planeacion_headers
):
    app, client = backend_client
    if app.state.db_engine is not None:
        pytest.skip("Esta mira la variante de memoria, que es la que tiene almacén propio.")
    if not os.getenv("TEST_DATABASE_URL"):
        pytest.skip("Sin TEST_DATABASE_URL no hay pozo de PostgreSQL que vigilar.")

    antes = await _ejercicios_en_la_base_de_pruebas()
    catalogo_id = await poa_inicial_id(client, planeacion_headers)
    primero = await crear_ejercicio_de_un_anio_libre(client, planeacion_headers, catalogo_id)
    segundo = await crear_ejercicio_de_un_anio_libre(client, planeacion_headers, catalogo_id)
    despues = await _ejercicios_en_la_base_de_pruebas()

    assert (primero["anio"], segundo["anio"]) == (
        primer_anio_por_venir(),
        primer_anio_por_venir() + 1,
    )
    assert despues == antes
