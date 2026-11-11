"""Dos POA conviven sin estorbarse, y editar uno no toca al otro."""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest

from app.modules.poa_planning.domain.cedula_entities import (
    PoaCatalogo,
    PoaStrategyCatalog,
)


@pytest.mark.asyncio
async def test_dos_poa_tienen_su_propia_estrategia_1_1(backend_client):
    """Lo que hoy es imposible. Y es la prueba que resume la entrega entera."""
    app, _ = backend_client
    repo = app.state.poa_form_repository
    inicial = await repo.ensure_catalogs()

    otro = await repo.save_catalog(
        PoaCatalogo.create(name=_nombre(), year=2027, origin="prueba", created_by=None)
    )
    await repo.save_objective(
        _objetivo(catalog_id=otro.id, number=1, key="OBJ-1", denomination="Objetivo")
    )
    await repo.save_strategy(
        PoaStrategyCatalog(
            catalog_id=otro.id,
            key="1.1",
            objective_number=1,
            denomination="La 1.1 del POA 2027",
        )
    )

    del_inicial = await repo.get_strategy(inicial, "1.1")
    del_otro = await repo.get_strategy(otro.id, "1.1")

    assert del_otro is not None
    assert del_otro.denomination == "La 1.1 del POA 2027"
    # Y la del POA inicial siguió donde estaba, sin enterarse.
    assert del_inicial is not None
    assert del_inicial.denomination != del_otro.denomination


@pytest.mark.asyncio
async def test_el_listado_sólo_trae_lo_del_poa_que_se_pide(backend_client):
    app, _ = backend_client
    repo = app.state.poa_form_repository
    await repo.ensure_catalogs()
    vacio = await repo.save_catalog(
        PoaCatalogo.create(name=_nombre(), year=2028, origin=None, created_by=None)
    )

    # Los cuatro listados llevan el mismo filtro de una línea, así que los
    # cuatro se piden: el asunto de la entrega es el aislamiento, y dos de
    # ellos se quedaban sin red.
    assert await repo.list_strategies(catalog_id=vacio.id) == []
    assert await repo.list_objectives(catalog_id=vacio.id) == []
    assert await repo.list_indicators(catalog_id=vacio.id) == []
    assert await repo.list_activity_catalog(catalog_id=vacio.id) == []


@pytest.mark.asyncio
async def test_el_poa_se_lista_se_busca_por_nombre_y_se_renombra_en_su_sitio(backend_client):
    """Los cinco métodos del POA, que son lo que el selector de Planeación va a
    consumir: listar, abrir por id, buscar por nombre, renombrar y marcar que su
    contenido cambió."""
    app, _ = backend_client
    repo = app.state.poa_form_repository
    inicial = await repo.ensure_catalogs()
    antes = len(await repo.list_catalogs())

    viejo, nuevo = _nombre(), _nombre()
    guardado = await repo.save_catalog(
        PoaCatalogo.create(name=viejo, year=2029, origin="prueba", created_by=None)
    )

    assert len(await repo.list_catalogs()) == antes + 1
    abierto = await repo.get_catalog(guardado.id)
    assert abierto is not None
    assert abierto.name == viejo
    assert abierto.year == 2029
    assert abierto.origin == "prueba"
    encontrado = await repo.get_catalog_by_name(viejo)
    assert encontrado is not None
    assert encontrado.id == guardado.id
    assert await repo.get_catalog_by_name(nuevo) is None

    # Renombrar es una edición en su sitio, no un POA de más: lo que Planeación
    # no quiere es que aparezcan dos «POA 2026» en el selector.
    #
    # Va sobre una *copia*, no mutando `abierto`: el adaptador en memoria
    # devuelve el mismo objeto que guarda, así que mutarlo renombraría el POA
    # almacenado antes de llamar a `save_catalog` y las aserciones de abajo
    # pasarían incluso con un `save_catalog` que no hiciera nada.
    await repo.save_catalog(replace(abierto, name=nuevo))
    assert len(await repo.list_catalogs()) == antes + 1
    assert await repo.get_catalog_by_name(viejo) is None
    renombrado = await repo.get_catalog_by_name(nuevo)
    assert renombrado is not None
    assert renombrado.id == guardado.id

    # Y el POA inicial no se enteró de nada de lo anterior.
    assert (await repo.get_catalog(inicial)) is not None


@pytest.mark.asyncio
async def test_arrancar_otra_vez_no_siembra_un_poa_de_mas(backend_client):
    """El guardián de `ensure_catalogs()`, que corre en cada arranque.

    Es lo único que impide que levantar la aplicación contra una base que ya
    tiene su POA le añada otro encima. Se verifica con más de un POA presente,
    porque lo que tiene que devolver es el inicial y no «alguno».
    """
    app, _ = backend_client
    repo = app.state.poa_form_repository
    inicial = await repo.ensure_catalogs()
    await repo.save_catalog(
        PoaCatalogo.create(name=_nombre(), year=2031, origin=None, created_by=None)
    )
    cuantos = len(await repo.list_catalogs())

    assert await repo.ensure_catalogs() == inicial
    assert len(await repo.list_catalogs()) == cuantos

    # Y el catálogo del POA inicial no se resembró encima de sí mismo.
    assert len(await repo.list_objectives(catalog_id=inicial)) == 6
    assert len(await repo.list_strategies(catalog_id=inicial)) == 24


@pytest.mark.asyncio
async def test_tocar_el_poa_mueve_su_ultima_modificacion(backend_client):
    app, _ = backend_client
    repo = app.state.poa_form_repository
    await repo.ensure_catalogs()
    poa = await repo.save_catalog(
        PoaCatalogo.create(name=_nombre(), year=2030, origin=None, created_by=None)
    )
    antes = (await repo.get_catalog(poa.id)).updated_at

    await repo.touch_catalog(poa.id)

    despues = (await repo.get_catalog(poa.id)).updated_at
    assert despues > antes


def _nombre() -> str:
    # El nombre del POA es único en la base, y la variante `postgresql` corre
    # contra una base real y persistente: un nombre fijo choca con el de la
    # corrida anterior.
    return f"POA de prueba {uuid4().hex[:6]}"


# Nota sobre `created_by=None`: `poa_catalogos.creado_por` es foránea a
# `usuarios`, y estas pruebas no crean usuarios -no les hace falta, lo que
# miden es que dos POA no se pisen-. Un id inventado reventaría la foránea en
# la variante `postgresql`. Es, además, con lo que `ensure_catalogs()` siembra
# el POA inicial: al arrancar todavía no hay nadie a quien atribuirlo.


def _objetivo(*, catalog_id: int, number: int, key: str, denomination: str):
    from app.modules.poa_planning.domain.cedula_entities import PoaObjectiveCatalog

    return PoaObjectiveCatalog(
        catalog_id=catalog_id, key=key, number=number, denomination=denomination
    )
