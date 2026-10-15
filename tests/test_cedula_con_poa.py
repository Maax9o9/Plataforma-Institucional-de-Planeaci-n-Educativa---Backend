"""La cédula guarda el POA de su ejercicio, y sus hijas lo heredan de ella.

Hasta aquí el catálogo era uno solo y la cédula no necesitaba decir de qué POA
era. Ahora la clave `1.1` vale dentro de un POA y no en todo el sistema, así
que la cédula lleva su `catalogo_id` -dato repetido a propósito- y la foránea
compuesta de la base impide que apunte al catálogo de otro año.

Lo que estas pruebas *no* tocan: los endpoints que resuelven nombres del
catálogo (el detalle de la cédula, el cuerpo del alta de un indicador o de una
actividad, los reportes). Esas consultas siguen llamando al puerto con la firma
vieja y son de la Tarea 7; aquí se llega al caso de uso por la fábrica que usa
el router, que es el mismo cableado sin el armado de la respuesta.
"""

from __future__ import annotations

import os
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.institutional_catalogs.domain.entities import Area
from app.modules.poa_planning.api.cedula_dependencies import (
    get_add_form_activity_use_case,
    get_add_form_indicator_use_case,
)
from app.modules.poa_planning.application.cedula_dto import (
    AddPoaFormActivityCommand,
    AddPoaFormIndicatorCommand,
)
from app.modules.poa_planning.domain.cedula_entities import (
    PoaActivityFollowUp,
    PoaForm,
)
from app.modules.poa_planning.infrastructure.cedula_sql_repository import (
    SqlAlchemyPoaFormRepository,
)
from app.shared.application.actor import ActorContext
from app.shared.domain.calendar import institutional_today
from helpers import (
    API,
    POA_INEXISTENTE,
    anio_libre,
    crear_ejercicio,
    crear_poa,
    poa_inicial_id,
)

#: El objetivo, la estrategia, el indicador y la acción que se dan de alta en
#: el POA nuevo. Ninguna de estas claves existe en el POA que siembra el
#: sistema: si la cédula resolviera el catálogo por otro lado, no se podría
#: crear. Y al revés, `_DEL_POA_SEMBRADO` sí existe allá y no aquí.
_OBJETIVO = 9
_ESTRATEGIA = "9.1"
_INDICADOR = "9.1.1"
_ACCION = "9.1.1"
_DEL_POA_SEMBRADO = "6.1"


async def _anio_formulable(client, headers) -> int:
    """Un año libre que todavía no empieza.

    La estructura de la cédula se cierra al terminar su primer cuatrimestre
    (`_ensure_structure_editable`), así que una cédula sólo se puede formular
    contra un ejercicio por venir. Se calcula desde el calendario institucional
    y no con un año fijo para que la prueba no caduque.
    """
    return await anio_libre(client, headers, desde=institutional_today().year + 1)


async def _poa_con_su_catalogo(client, headers) -> tuple[dict, int]:
    """Un POA nuevo con su objetivo, su estrategia, su indicador y su acción,
    y el año libre del que colgará el ejercicio."""
    anio = await _anio_formulable(client, headers)
    poa = await crear_poa(client, headers, anio)
    catalogo = {"catalogo_id": poa["id"]}
    objetivo = await client.post(
        f"{API}/poa/catalogos/objetivos/{_OBJETIVO}",
        headers=headers,
        params=catalogo,
        json={"clave": f"OBJ-{_OBJETIVO}", "denominacion": "El objetivo de este POA"},
    )
    assert objetivo.status_code == 201, objetivo.text
    estrategia = await client.post(
        f"{API}/poa/catalogos/estrategias/{_ESTRATEGIA}",
        headers=headers,
        params=catalogo,
        json={"objetivo_numero": _OBJETIVO, "denominacion": f"La {_ESTRATEGIA} de este POA"},
    )
    assert estrategia.status_code == 201, estrategia.text
    indicador = await client.post(
        f"{API}/poa/catalogos/indicadores/{_INDICADOR}",
        headers=headers,
        params=catalogo,
        json={
            "objetivo_numero": _OBJETIVO,
            "nombre": f"El indicador {_INDICADOR} de este POA",
            "formula": "Los que hay entre los que debería haber, por cien",
            "unidad_medida": "Porcentaje",
        },
    )
    assert indicador.status_code == 201, indicador.text
    accion = await client.post(
        f"{API}/poa/catalogos/actividades/{_ACCION}",
        headers=headers,
        params=catalogo,
        json={
            "estrategia_clave": _ESTRATEGIA,
            "descripcion": f"La acción {_ACCION} de este POA",
        },
    )
    assert accion.status_code == 201, accion.text
    return poa, anio


async def _area(app) -> int:
    """Un área responsable propia, por el repositorio de la aplicación.

    El alta por HTTP es de `admin_sistema` y aquí sólo hay cabeceras de
    Planeación; el área es decorado de la prueba, no lo que se prueba.
    """
    sufijo = uuid4().hex[:8]
    area = Area.create(code=f"T6B-{sufijo}", name=f"Área responsable {sufijo}")
    await app.state.area_repository.add(area)
    return area.id


def _cuatrimestres(anio: int) -> list[dict[str, object]]:
    return [
        {"numero": 1, "fecha_inicio": f"{anio}-01-01", "fecha_fin": f"{anio}-04-30"},
        {"numero": 2, "fecha_inicio": f"{anio}-05-01", "fecha_fin": f"{anio}-08-31"},
        {"numero": 3, "fecha_inicio": f"{anio}-09-01", "fecha_fin": f"{anio}-12-31"},
    ]


async def _crear_cedula(client, headers, *, ejercicio: int, anio: int, area: int, clave: str):
    return await client.post(
        f"{API}/poa/cedulas",
        headers=headers,
        json={
            "ejercicio_id": ejercicio,
            "estrategia_clave": clave,
            "area_responsable_id": area,
            "alcance_efecto_socioeconomico": "Lo que se espera lograr.",
            "cuatrimestres": _cuatrimestres(anio),
        },
    )


async def _escenario(client, headers, app) -> tuple[dict, dict, int]:
    """El POA con su catálogo, el ejercicio que cuelga de él y un área."""
    poa, anio = await _poa_con_su_catalogo(client, headers)
    ejercicio = await crear_ejercicio(client, headers, poa, anio)
    return poa, ejercicio, await _area(app)


def _peticion(app):
    """Lo único que las fábricas de `cedula_dependencies` le piden a la
    petición es la aplicación.

    Se usan las fábricas de verdad, y no una composición propia, para que la
    prueba ejercite el mismo cableado que el router: lo que queda fuera es
    nada más el armado de la respuesta, que resuelve nombres del catálogo y es
    de la Tarea 7.
    """
    return SimpleNamespace(app=app)


def _planeacion(cedula: dict) -> ActorContext:
    """El actor de Planeación que creó la cédula. Su id sale de la cédula para
    que sea un usuario que existe de verdad (`poa_cedulas.creado_por` es
    foránea a `usuarios`)."""
    return ActorContext(id=cedula["creado_por"], roles=frozenset({"planeacion"}), area_id=None)


@pytest.mark.asyncio
async def test_crear_una_cedula_guarda_el_poa_de_su_ejercicio(backend_client, planeacion_headers):
    """`poa_cedulas.catalogo_id` es NOT NULL y sin valor por omisión: sin
    escribirlo no se puede crear una cédula contra PostgreSQL."""
    app, client = backend_client
    poa, ejercicio, area = await _escenario(client, planeacion_headers, app)

    creada = await _crear_cedula(
        client,
        planeacion_headers,
        ejercicio=ejercicio["id"],
        anio=ejercicio["anio"],
        area=area,
        clave=_ESTRATEGIA,
    )

    assert creada.status_code == 201, creada.text
    guardada = await app.state.poa_form_repository.get_form(creada.json()["id"])
    assert guardada is not None
    assert guardada.catalog_id == poa["id"]


@pytest.mark.asyncio
async def test_la_cedula_resuelve_su_estrategia_en_el_catalogo_de_su_ejercicio(
    backend_client, planeacion_headers
):
    """Las dos caras del aislamiento: la estrategia que sólo existe en el POA
    del ejercicio se puede elegir, y la que sólo existe en otro POA no."""
    app, client = backend_client
    _, ejercicio, area = await _escenario(client, planeacion_headers, app)
    # La clave ajena tiene que existir *en algún sitio*, o el 404 de abajo
    # pasaría por no existir en ninguno y no probaría el aislamiento.
    sembrado = await client.get(
        f"{API}/poa/catalogos/estrategias",
        headers=planeacion_headers,
        params={"catalogo_id": await poa_inicial_id(client, planeacion_headers)},
    )
    assert sembrado.status_code == 200, sembrado.text
    assert _DEL_POA_SEMBRADO in [item["clave"] for item in sembrado.json()]

    propia = await _crear_cedula(
        client,
        planeacion_headers,
        ejercicio=ejercicio["id"],
        anio=ejercicio["anio"],
        area=area,
        clave=_ESTRATEGIA,
    )
    ajena = await _crear_cedula(
        client,
        planeacion_headers,
        ejercicio=ejercicio["id"],
        anio=ejercicio["anio"],
        area=await _area(app),
        clave=_DEL_POA_SEMBRADO,
    )

    assert propia.status_code == 201, propia.text
    # El objetivo no viene en la petición: lo deduce el caso de uso de la
    # estrategia que encontró, así que dice en qué catálogo la buscó.
    assert propia.json()["objetivo_numero"] == _OBJETIVO
    assert ajena.status_code == 404, ajena.text


@pytest.mark.asyncio
async def test_el_indicador_y_la_actividad_heredan_el_poa_de_su_cedula(
    backend_client, planeacion_headers
):
    """Las dos tablas hijas también llevan `catalogo_id` NOT NULL, y su
    foránea compuesta contra la cédula exige que sea el mismo."""
    app, client = backend_client
    poa, ejercicio, area = await _escenario(client, planeacion_headers, app)
    creada = await _crear_cedula(
        client,
        planeacion_headers,
        ejercicio=ejercicio["id"],
        anio=ejercicio["anio"],
        area=area,
        clave=_ESTRATEGIA,
    )
    assert creada.status_code == 201, creada.text
    cedula = creada.json()
    actor = _planeacion(cedula)
    repositorio = app.state.poa_form_repository

    indicador = await get_add_form_indicator_use_case(_peticion(app)).execute(
        AddPoaFormIndicatorCommand(
            form_id=cedula["id"],
            indicator_key=_INDICADOR,
            institutional_goal=Decimal(10),
            baseline_year=None,
            baseline_value=None,
            current_percentage=None,
            target_value=None,
            target_percentage=None,
            actor=actor,
        )
    )
    actividad = await get_add_form_activity_use_case(_peticion(app)).execute(
        AddPoaFormActivityCommand(
            form_id=cedula["id"],
            activity_key=_ACCION,
            unit="Documento",
            annual_goal=Decimal(1),
            executing_area_id=None,
            observations=None,
            actor=actor,
        )
    )

    assert indicador.catalog_id == poa["id"]
    assert actividad.catalog_id == poa["id"]
    # Y vuelve a leerse de donde se guardó, que es lo que los ocho sitios del
    # router van a consultar para saber de qué POA leer el nombre.
    releido_indicador = await repositorio.get_form_indicator(indicador.id)
    releida_actividad = await repositorio.get_form_activity(actividad.id)
    assert releido_indicador.catalog_id == poa["id"]
    assert releida_actividad.catalog_id == poa["id"]


@pytest.mark.asyncio
async def test_la_tarjeta_del_tablero_dice_de_que_poa_es(backend_client, planeacion_headers):
    """La tarjeta es un modelo de lectura y el tablero resuelve descripciones
    sin abrir la cédula de cada una: necesita el POA en la tarjeta."""
    app, client = backend_client
    poa, ejercicio, area = await _escenario(client, planeacion_headers, app)
    creada = await _crear_cedula(
        client,
        planeacion_headers,
        ejercicio=ejercicio["id"],
        anio=ejercicio["anio"],
        area=area,
        clave=_ESTRATEGIA,
    )
    assert creada.status_code == 201, creada.text
    cedula = creada.json()
    repositorio = app.state.poa_form_repository
    actividad = await get_add_form_activity_use_case(_peticion(app)).execute(
        AddPoaFormActivityCommand(
            form_id=cedula["id"],
            activity_key=_ACCION,
            unit="Documento",
            annual_goal=Decimal(1),
            executing_area_id=None,
            observations=None,
            actor=_planeacion(cedula),
        )
    )
    await repositorio.upsert_follow_up(
        PoaActivityFollowUp.create(
            form_activity_id=actividad.id,
            quarter=1,
            period_id=cedula["cuatrimestres"][0]["periodo_id"],
            captured_by=cedula["creado_por"],
            scheduled=Decimal(1),
        )
    )

    tarjetas, total = await repositorio.list_follow_up_cards(exercise_id=ejercicio["id"])

    assert total == 1
    assert tarjetas[0].catalog_id == poa["id"]


@pytest.mark.asyncio
async def test_una_cedula_repetida_sigue_siendo_un_conflicto(backend_client, planeacion_headers):
    """La misma estrategia, el mismo área y el mismo ejercicio: eso sí es un
    duplicado, y el 409 que lo dice tiene que sobrevivir a que `add_form`
    deje de traducir cualquier violación."""
    app, client = backend_client
    _, ejercicio, area = await _escenario(client, planeacion_headers, app)
    argumentos = {
        "ejercicio": ejercicio["id"],
        "anio": ejercicio["anio"],
        "area": area,
        "clave": _ESTRATEGIA,
    }

    primera = await _crear_cedula(client, planeacion_headers, **argumentos)
    repetida = await _crear_cedula(client, planeacion_headers, **argumentos)

    assert primera.status_code == 201, primera.text
    assert repetida.status_code == 409, repetida.text


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL no configurada")
@pytest.mark.asyncio
async def test_guardar_una_cedula_de_un_poa_que_no_existe_no_es_un_duplicado():
    """Un `except IntegrityError` que traduce *todo* a «ya existe una cédula»
    manda a buscar un duplicado cuando lo que falló fue la foránea del POA.

    Se prueba contra el adaptador de PostgreSQL porque es ahí donde vive la
    traducción: la variante en memoria no tiene foráneas que violar.
    """
    motor = create_async_engine(os.environ["TEST_DATABASE_URL"])
    try:
        repositorio = SqlAlchemyPoaFormRepository(async_sessionmaker(motor, expire_on_commit=False))
        cedula = PoaForm.create(
            catalog_id=POA_INEXISTENTE,
            exercise_id=POA_INEXISTENTE,
            objective_number=1,
            strategy_key="1.1",
            responsible_area_id=POA_INEXISTENTE,
            created_by=POA_INEXISTENTE,
        )

        with pytest.raises(IntegrityError):
            await repositorio.add_form(cedula)
    finally:
        await motor.dispose()
