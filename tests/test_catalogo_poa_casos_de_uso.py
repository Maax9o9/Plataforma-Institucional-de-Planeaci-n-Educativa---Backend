"""Crear POAs, y que editar su contenido mueva su fecha."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.poa_planning.application.use_cases.manage_catalog import PoaCatalogAdmin
from app.modules.poa_planning.application.use_cases.manage_poa_catalog import (
    CrearCatalogoPoa,
    ListarCatalogosPoa,
)
from app.modules.poa_planning.domain.cedula_entities import PoaCatalogo
from app.modules.poa_planning.infrastructure.cedula_repository import (
    InMemoryPoaFormRepository,
)
from app.shared.application.actor import ActorContext
from app.shared.domain.exceptions import ConflictError, ForbiddenError, ValidationError

PLANEACION = ActorContext(id=1, roles=frozenset({"planeacion"}), area_id=None)
AREA = ActorContext(id=2, roles=frozenset({"capturista_poa"}), area_id=3)


@pytest.mark.asyncio
async def test_dos_poa_no_pueden_llamarse_igual():
    """El nombre es lo que lo identifica en el selector: repetirlo dejaría a
    Planeación eligiendo a ciegas. Llega como conflicto con el nombre dentro,
    no como un error de restricción de la base."""
    repo = InMemoryPoaFormRepository()
    await repo.ensure_catalogs()
    caso = CrearCatalogoPoa(repo)
    await caso.execute(name="POA 2027", year=2027, origin=None, actor=PLANEACION)

    with pytest.raises(ConflictError) as fallo:
        await caso.execute(name="POA 2027", year=2027, origin=None, actor=PLANEACION)

    assert "POA 2027" in str(fallo.value)


@pytest.mark.asyncio
async def test_el_caso_de_uso_ni_intenta_guardar_un_nombre_repetido():
    """La comprobación del caso de uso es la primera cerradura; la del
    repositorio, la segunda, la que cubre dos altas simultáneas. Como las dos
    dan el mismo conflicto, la prueba de arriba no distingue cuál respondió:
    ésta sí, porque exige que el repetido ni llegue a guardarse."""
    repo = InMemoryPoaFormRepository()
    await repo.ensure_catalogs()
    caso = CrearCatalogoPoa(repo)
    await caso.execute(name="POA 2027", year=2027, origin=None, actor=PLANEACION)
    intentos: list[str] = []
    guardar = repo.save_catalog

    async def guardar_y_anotar(item):
        intentos.append(item.name)
        return await guardar(item)

    repo.save_catalog = guardar_y_anotar

    with pytest.raises(ConflictError):
        await caso.execute(name="POA 2027", year=2027, origin=None, actor=PLANEACION)

    assert intentos == []


@pytest.mark.asyncio
async def test_sólo_planeación_crea_un_poa():
    repo = InMemoryPoaFormRepository()
    await repo.ensure_catalogs()

    with pytest.raises(ForbiddenError):
        await CrearCatalogoPoa(repo).execute(
            name="POA del área", year=2027, origin=None, actor=AREA
        )


@pytest.mark.asyncio
async def test_cualquiera_puede_listar_los_poa():
    """Leer no se restringe: el selector lo necesita quien formula o consulta,
    no sólo Planeación."""
    repo = InMemoryPoaFormRepository()
    inicial = await repo.ensure_catalogs()
    nuevo = await CrearCatalogoPoa(repo).execute(
        name="POA 2027", year=2027, origin=None, actor=PLANEACION
    )

    vistos = await ListarCatalogosPoa(repo).execute(AREA)

    assert [poa.id for poa in vistos] == [inicial, nuevo.id]


@pytest.mark.asyncio
async def test_editar_una_estrategia_mueve_la_fecha_de_su_poa():
    """Es la fecha que Planeación pidió ver, y lo que ella entiende por
    «última modificación» es que alguien tocó una estrategia."""
    repo = InMemoryPoaFormRepository()
    inicial = await repo.ensure_catalogs()
    antes = (await repo.get_catalog(inicial)).updated_at

    await PoaCatalogAdmin(repo).save_strategy(
        catalog_id=inicial,
        key="1.1",
        objective_number=1,
        denomination="Texto corregido",
        is_active=True,
        actor=PLANEACION,
        creating=False,
    )

    assert (await repo.get_catalog(inicial)).updated_at > antes


@pytest.mark.asyncio
@pytest.mark.parametrize("que", ["objetivo", "indicador", "acción"])
async def test_las_otras_tres_ediciones_del_catálogo_también_mueven_la_fecha(que):
    """La estrategia ya la cubre la prueba de arriba. Las otras tres llevan su
    propia llamada a `touch_catalog`, y olvidar una dejaría a Planeación viendo
    una fecha que no se mueve justo al editar esa parte."""
    repo = InMemoryPoaFormRepository()
    inicial = await repo.ensure_catalogs()
    antes = (await repo.get_catalog(inicial)).updated_at
    admin = PoaCatalogAdmin(repo)

    if que == "objetivo":
        await admin.save_objective(
            catalog_id=inicial,
            number=1,
            key="OBJ-1",
            denomination="Texto corregido",
            is_active=True,
            actor=PLANEACION,
            creating=False,
        )
    elif que == "indicador":
        await admin.save_indicator(
            catalog_id=inicial,
            key="1.1.14",
            objective_number=1,
            name="Texto corregido",
            formula="Fórmula",
            unit="Porcentaje",
            is_active=True,
            actor=PLANEACION,
            creating=False,
        )
    else:
        await admin.save_activity(
            catalog_id=inicial,
            key="1.1.2",
            strategy_key="1.1",
            description="Texto corregido",
            is_active=True,
            actor=PLANEACION,
            creating=False,
        )

    assert (await repo.get_catalog(inicial)).updated_at > antes


@pytest.mark.asyncio
async def test_si_el_guardado_falla_la_fecha_del_poa_no_se_mueve():
    """La fecha se mueve al terminar, no al empezar: lo que Planeación entiende
    por «última modificación» es que alguien tocó una estrategia, no que
    alguien lo intentó."""
    repo = InMemoryPoaFormRepository()
    inicial = await repo.ensure_catalogs()
    antes = (await repo.get_catalog(inicial)).updated_at

    # El objetivo 99 no existe: el caso de uso rechaza el alta antes de guardar.
    with pytest.raises(ValidationError):
        await PoaCatalogAdmin(repo).save_strategy(
            catalog_id=inicial,
            key="9.9",
            objective_number=99,
            denomination="Nunca se guarda",
            is_active=True,
            actor=PLANEACION,
            creating=True,
        )

    assert (await repo.get_catalog(inicial)).updated_at == antes


@pytest.mark.asyncio
async def test_editar_un_poa_no_toca_a_otro():
    """Lo que Planeación pidió textualmente: que cambiar la información de un
    POA no cambie la del 2026. Crear la «1.1» del 2027 es un alta aunque la
    «1.1» del 2026 ya exista, y no mueve la fecha del 2026."""
    repo = InMemoryPoaFormRepository()
    inicial = await repo.ensure_catalogs()
    antes = await repo.get_catalog(inicial)
    fecha_antes, estrategia_antes = antes.updated_at, await repo.get_strategy(inicial, "1.1")
    otro = await CrearCatalogoPoa(repo).execute(
        name="POA 2027", year=2027, origin=None, actor=PLANEACION
    )
    admin = PoaCatalogAdmin(repo)

    await admin.save_objective(
        catalog_id=otro.id,
        number=1,
        key="OBJ-1",
        denomination="Objetivo del 2027",
        is_active=True,
        actor=PLANEACION,
        creating=True,
    )
    await admin.save_strategy(
        catalog_id=otro.id,
        key="1.1",
        objective_number=1,
        denomination="La 1.1 del 2027",
        is_active=True,
        actor=PLANEACION,
        creating=True,
    )

    assert (await repo.get_strategy(inicial, "1.1")) == estrategia_antes
    assert (await repo.get_catalog(inicial)).updated_at == fecha_antes
    assert (await repo.get_catalog(otro.id)).updated_at > otro.created_at


# --- El repositorio, sin pasar por el caso de uso ---------------------------


def _nombre() -> str:
    # El nombre del POA es único en la base, y la variante `postgresql` corre
    # contra una base real y persistente: un nombre fijo choca con el de la
    # corrida anterior.
    return f"POA de prueba {uuid4().hex[:6]}"


@pytest.mark.asyncio
async def test_dos_altas_que_se_cuelan_juntas_tambien_dan_conflicto_con_el_nombre(
    backend_client,
):
    """El caso de uso comprueba el nombre antes de guardar, pero dos altas a la
    vez pasan las dos esa comprobación. La segunda tiene que llegar como
    conflicto con el nombre dentro y no como un error de restricción de la
    base: por eso aquí se llama al repositorio directo, saltándose al caso de
    uso."""
    app, _ = backend_client
    repo = app.state.poa_form_repository
    await repo.ensure_catalogs()
    nombre = _nombre()
    await repo.save_catalog(
        PoaCatalogo.create(name=nombre, year=2027, origin=None, created_by=None)
    )

    with pytest.raises(ConflictError) as fallo:
        await repo.save_catalog(
            PoaCatalogo.create(name=nombre, year=2028, origin=None, created_by=None)
        )

    assert nombre in str(fallo.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("backend_client", ["postgresql"], indirect=True)
async def test_un_creador_inexistente_no_se_hace_pasar_por_nombre_repetido(backend_client):
    """Sólo en PostgreSQL: la memoria no tiene llaves foráneas.

    Cualquier otra violación de restricción tiene que llegar tal cual. Decir
    «ya existe un POA con ese nombre» cuando lo que falló fue la foránea a
    `usuarios` manda a quien depura a buscar un duplicado que no existe."""
    app, _ = backend_client
    repo = app.state.poa_form_repository
    await repo.ensure_catalogs()

    with pytest.raises(IntegrityError) as fallo:
        await repo.save_catalog(
            PoaCatalogo.create(name=_nombre(), year=2027, origin=None, created_by=2_000_000_000)
        )

    assert "poa_catalogos_creado_por_fkey" in str(fallo.value)
