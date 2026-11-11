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

from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.identity_access.domain.value_objects import Role
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
from app.modules.poa_planning.domain.entities import PoaExercise
from app.shared.application.actor import ActorContext
from app.shared.domain.calendar import institutional_today
from app.shared.domain.exceptions import ValidationError
from app.shared.infrastructure.db.constraints import viola_la_restriccion
from helpers import (
    API,
    POA_INEXISTENTE,
    anio_libre,
    crear_ejercicio,
    crear_poa,
    cuatrimestres,
    poa_inicial_id,
)
from test_ciclo_poa import _account
from test_poa_cedula_flow import _attach_follow_up_file, _open_poa_period

#: Las dos foráneas compuestas que existen para que una cédula no pueda apuntar
#: al catálogo de otro año. Cuál de las dos reporta PostgreSQL cuando las dos
#: están violadas depende del orden en que dispara los disparadores, y eso no es
#: contrato: la prueba afirma que es una de ellas, no cuál.
_FORANEAS_DEL_POA = ("fk_poa_cedula_ejercicio_catalogo", "fk_poa_cedula_estrategia")

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


async def _crear_cedula(
    client, headers, *, ejercicio: int, anio: int, area: int, clave: str, **extra
):
    """El POST de la cédula. `extra` es para lo que una prueba concreta
    necesite añadir al cuerpo -el tipo de estrategia y los firmantes, que la
    emisión exige-."""
    return await client.post(
        f"{API}/poa/cedulas",
        headers=headers,
        json={
            "ejercicio_id": ejercicio,
            "estrategia_clave": clave,
            "area_responsable_id": area,
            "alcance_efecto_socioeconomico": "Lo que se espera lograr.",
            "cuatrimestres": cuatrimestres(anio),
            **extra,
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


@pytest.mark.parametrize("backend_client", ["postgresql"], indirect=True)
@pytest.mark.asyncio
async def test_una_cedula_que_apunta_al_poa_equivocado_no_se_reporta_como_duplicada(
    backend_client, planeacion_headers
):
    """Un `except IntegrityError` que traduce *todo* a «ya existe una cédula»
    manda a buscar un duplicado cuando lo que falló fue la foránea del POA.

    Sólo contra PostgreSQL -de ahí el `backend_client` fijado a esa variante-,
    porque es donde vive la traducción y donde hay foráneas que violar; la
    variante en memoria no tiene ninguna. Con la URL puesta corre; sin ella se
    salta diciéndolo, igual que el resto de las pruebas de PostgreSQL.

    El escenario es real salvo el POA: el ejercicio existe, el área existe y el
    usuario existe, así que la única violación posible es la del catálogo. Si
    se dejaran también esos ids inventados, la restricción que PostgreSQL
    reportaría primero sería cualquiera de sus foráneas sueltas y la prueba no
    diría lo que su nombre promete.
    """
    app, client = backend_client
    _, ejercicio, area = await _escenario(client, planeacion_headers, app)
    # Una cédula de verdad, para tomar de ella el id de un usuario que existe.
    legitima = await _crear_cedula(
        client,
        planeacion_headers,
        ejercicio=ejercicio["id"],
        anio=ejercicio["anio"],
        area=area,
        clave=_ESTRATEGIA,
    )
    assert legitima.status_code == 201, legitima.text
    extraviada = PoaForm.create(
        catalog_id=POA_INEXISTENTE,
        exercise_id=ejercicio["id"],
        objective_number=_OBJETIVO,
        strategy_key=_ESTRATEGIA,
        # Otro área, para que un 409 legítimo no pueda hacerse pasar por el que
        # se está buscando.
        responsible_area_id=await _area(app),
        created_by=legitima.json()["creado_por"],
    )

    with pytest.raises(IntegrityError) as fallo:
        await app.state.poa_form_repository.add_form(extraviada)

    assert any(viola_la_restriccion(fallo.value, nombre) for nombre in _FORANEAS_DEL_POA), (
        fallo.value
    )


@pytest.mark.asyncio
async def test_la_emision_respalda_los_nombres_del_poa_de_su_cedula(
    backend_client, planeacion_headers
):
    """El único camino del cambio donde la base no ataja una resolución
    equivocada.

    Las escrituras las frenan las foráneas compuestas: una cédula, un indicador
    o una actividad que apunten al catálogo de otro año no entran. El respaldo
    cuatrimestral, en cambio, es un `dict` en una columna JSON: si
    `_build_snapshot` resolviera los nombres en el POA equivocado, la emisión
    se guardaría con el texto de otro año y nadie se enteraría. Es exactamente
    el defecto que toda esta entrega existe para cerrar.

    Una sola emisión cubre las cuatro consultas al catálogo que hace
    `_build_snapshot`: el objetivo, la estrategia, el indicador y la acción.
    """
    app, client = backend_client
    poa, ejercicio, area = await _escenario(client, planeacion_headers, app)
    creada = await _crear_cedula(
        client,
        planeacion_headers,
        ejercicio=ejercicio["id"],
        anio=ejercicio["anio"],
        area=area,
        clave=_ESTRATEGIA,
        # Lo que `emission_errors` exige además de un indicador, una actividad
        # y su seguimiento completo con evidencia.
        tipo_estrategia="Eficacia",
        firmantes=[
            {"nombre": "Titular Rectoría", "cargo": "Rectoría"},
            {"nombre": "Titular Planeación", "cargo": "Dirección de Planeación"},
        ],
    )
    assert creada.status_code == 201, creada.text
    cedula = creada.json()
    peticion = _peticion(app)
    await get_add_form_indicator_use_case(peticion).execute(
        AddPoaFormIndicatorCommand(
            form_id=cedula["id"],
            indicator_key=_INDICADOR,
            institutional_goal=Decimal(10),
            baseline_year=None,
            baseline_value=None,
            current_percentage=None,
            target_value=None,
            target_percentage=None,
            actor=_planeacion(cedula),
        )
    )
    actividad = await get_add_form_activity_use_case(peticion).execute(
        AddPoaFormActivityCommand(
            form_id=cedula["id"],
            activity_key=_ACCION,
            unit="Documento",
            annual_goal=Decimal(1),
            executing_area_id=area,
            observations=None,
            actor=_planeacion(cedula),
        )
    )

    # El informe del cuatrimestre lo escribe el área, no Planeación
    # (`can_report_progress`), así que hace falta un capturista del área.
    periodo_id = cedula["cuatrimestres"][0]["periodo_id"]
    await _open_poa_period(client, planeacion_headers, periodo_id)
    _, capturista = await _account(app, client, Role.CAPTURISTA_POA, uuid4().hex[:8], area_id=area)
    seguimiento = await client.put(
        f"{API}/poa/cedulas/actividades/{actividad.id}/seguimientos/1",
        headers=capturista,
        json={
            "periodo_id": periodo_id,
            "programado": 1,
            "alcanzado": 1,
            "progreso": "Documento entregado",
            "alcance": "Comunidad universitaria",
        },
    )
    assert seguimiento.status_code == 200, seguimiento.text
    await _attach_follow_up_file(
        client,
        capturista,
        seguimiento.json()["id"],
        f"t6b-{uuid4().hex[:6]}",
        f"{ejercicio['anio']}-04-30",
    )

    emision = await client.post(
        f"{API}/poa/cedulas/{cedula['id']}/emisiones",
        headers=planeacion_headers,
        json={"cuatrimestre": 1, "periodo_id": periodo_id},
    )

    assert emision.status_code == 201, emision.text
    respaldo = emision.json()["snapshot"]
    estrategia = respaldo["seccion_1_estrategia"]
    # Las cuatro consultas de `_build_snapshot`, una por aserción. Los textos
    # son los del POA `9.x` que esta prueba creó: el POA que siembra el sistema
    # no tiene ninguna de estas cuatro claves.
    # Las llaves del respaldo son los nombres de campo de las entidades, que es
    # lo que `asdict` produce: `denomination`, `name`, `description`.
    assert estrategia["objetivo"]["denomination"] == "El objetivo de este POA"
    assert estrategia["estrategia"]["denomination"] == f"La {_ESTRATEGIA} de este POA"
    assert estrategia["estrategia"]["catalog_id"] == poa["id"]
    assert (
        respaldo["seccion_2_indicadores"][0]["catalogo"]["name"]
        == f"El indicador {_INDICADOR} de este POA"
    )
    assert (
        respaldo["seccion_4_calendarizacion_y_seguimiento"][0]["catalogo"]["description"]
        == f"La acción {_ACCION} de este POA"
    )


@pytest.mark.parametrize("catalogo_id", [0, -1], ids=["cero", "negativo"])
def test_un_poa_que_no_puede_ser_no_se_acepta_ni_en_la_cedula_ni_en_el_ejercicio(catalogo_id):
    """Los seriales de la base empiezan en 1, así que el cero y los negativos no
    son ids de POA. Las dos entidades lo rechazan con el mismo criterio que
    `IdDePoa` aplica en el borde HTTP, para que quien entre por otro lado -una
    migración, un script, una prueba- no cuelgue filas de un POA imposible."""
    with pytest.raises(ValidationError):
        PoaForm.create(
            catalog_id=catalogo_id,
            exercise_id=1,
            objective_number=1,
            strategy_key="1.1",
            responsible_area_id=1,
            created_by=1,
        )
    with pytest.raises(ValidationError):
        PoaExercise.create(2030, catalog_id=catalogo_id)
