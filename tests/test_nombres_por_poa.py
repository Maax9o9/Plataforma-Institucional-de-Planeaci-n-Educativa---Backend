"""Ningún consumidor del catálogo resuelve un nombre sin decir de qué POA.

Son las pruebas que resumen la entrega. El catálogo del POA era uno solo -la
clave `1.1` era llave primaria global-, así que corregir el texto de una
estrategia reescribía lo que mostraban las cédulas de todos los años.
Planeación lo dijo así: «lo que no quiero, que cambiando la información de las
cédulas, esto cambie la que contiene el 2026».

Las escrituras ya las ataja la base -las foráneas compuestas impiden que una
cédula, un indicador o una actividad cuelguen del catálogo de otro año-. Lo que
queda son las **lecturas que resuelven nombres**, y de ésas aquí están las
cuatro que nada cubría: el detalle de la cédula, el tablero de seguimiento -el
listado y la tarjeta suelta, que se arman igual pero se piden por separado-, el
servicio de reportes y el formato de la SEP. El tablero y los reportes son los
difíciles, porque pueden abarcar varios POAs a la vez: `ejercicio_id` es
opcional en los dos. El formato de la SEP está acotado a un ejercicio, y aun así
no lo cubría nada: `test_formato_sep.py` ejercita `llenar_formato` sobre cédulas
armadas a mano y **nunca llama a `ExportarFormatoSep.execute()`**, que es donde
se decide de qué POA salen los nombres. Esa afirmación estuvo escrita aquí y era
falsa; la prueba que faltaba es la última de este archivo.

Cada prueba crea **dos POAs con la misma clave y texto distinto**. Es lo único
que distingue «resolví en el POA de esta cédula» de «resolví en el primero que
encontré»: con el mismo texto en los dos, las dos implementaciones pasarían.
"""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import load_workbook

from app.modules.poa_planning.domain.cedula_entities import PoaActivityFollowUp
from app.modules.poa_reports.application.sep_format import localizar_bloques
from helpers import API, crear_ejercicio, crear_poa
from test_cedula_con_poa import _anio_formulable, _area, _crear_cedula

#: El objetivo, la estrategia y la acción que cada POA de estas pruebas se da
#: de alta, con las claves del POA que siembra el sistema a propósito.
#:
#: `1.1` existe también en el POA sembrado -con otro texto-, así que una
#: resolución que se vaya al POA equivocado devuelve un texto distinto en vez de
#: estallar, que es la falla que estas pruebas tienen que poder ver. `1.1.1`, en
#: cambio, no existe entre las 150 acciones sembradas (`reference_data.py`): si
#: el tablero o el reporte la buscaran en el catálogo del POA sembrado no la
#: encontrarían y caerían al valor por omisión, que es la clave.
_OBJETIVO = 1
_ESTRATEGIA = "1.1"
_ACCION = "1.1.1"

#: El indicador, elegido con el criterio opuesto al de la acción: `1.1.14` **sí**
#: existe entre los 11 sembrados (`reference_data.py`), con el nombre de la SEP y
#: el objetivo 1. Así, resolverlo en el POA equivocado devuelve un texto distinto
#: en vez de quedarse vacío, que es más difícil de confundir con un fallo de
#: armado.
_INDICADOR = "1.1.14"


async def _poa_con_catalogo(client, headers, *, anio: int, texto: str) -> dict:
    """Un POA nuevo con su objetivo, su estrategia, su indicador y su acción
    propios.

    `texto` entra en las cuatro denominaciones y es lo que cada prueba compara:
    las claves son iguales en los dos POAs que crea, el texto no.
    """
    poa = await crear_poa(client, headers, anio)
    catalogo = {"catalogo_id": poa["id"]}
    objetivo = await client.post(
        f"{API}/poa/catalogos/objetivos/{_OBJETIVO}",
        headers=headers,
        params=catalogo,
        json={"clave": f"OBJ-{_OBJETIVO}", "denominacion": f"El objetivo {texto}"},
    )
    assert objetivo.status_code == 201, objetivo.text
    estrategia = await client.post(
        f"{API}/poa/catalogos/estrategias/{_ESTRATEGIA}",
        headers=headers,
        params=catalogo,
        json={
            "objetivo_numero": _OBJETIVO,
            "denominacion": f"La {_ESTRATEGIA} {texto}",
        },
    )
    assert estrategia.status_code == 201, estrategia.text
    indicador = await client.post(
        f"{API}/poa/catalogos/indicadores/{_INDICADOR}",
        headers=headers,
        params=catalogo,
        json={
            "objetivo_numero": _OBJETIVO,
            "nombre": f"El indicador {_INDICADOR} {texto}",
            "formula": "(a / b) * 100",
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
            "descripcion": f"La acción {_ACCION} {texto}",
        },
    )
    assert accion.status_code == 201, accion.text
    return poa


async def _poa_con_su_ejercicio(client, headers, *, texto: str) -> tuple[dict, dict]:
    """El POA con su catálogo y el ejercicio que cuelga de él.

    El año sale de `anio_libre` -por `_anio_formulable`- y no de un literal:
    `poa_ejercicios.anio` es único en todo el sistema y la base de PostgreSQL
    persiste durante la corrida, así que un 2040 fijo choca con la prueba de al
    lado. Dos llamadas seguidas dan dos años distintos, porque el ejercicio de
    la primera ya ocupa el suyo.
    """
    anio = await _anio_formulable(client, headers)
    poa = await _poa_con_catalogo(client, headers, anio=anio, texto=texto)
    return poa, await crear_ejercicio(client, headers, poa, anio)


async def _cedula_con_su_accion(client, headers, *, ejercicio: dict, area: int) -> dict:
    """La cédula de la estrategia `1.1` del ejercicio, con la acción `1.1.1`
    agregada y el área como ejecutora."""
    creada = await _crear_cedula(
        client,
        headers,
        ejercicio=ejercicio["id"],
        anio=ejercicio["anio"],
        area=area,
        clave=_ESTRATEGIA,
    )
    assert creada.status_code == 201, creada.text
    cedula = creada.json()
    actividad = await client.post(
        f"{API}/poa/cedulas/{cedula['id']}/actividades",
        headers=headers,
        json={
            "actividad_clave": _ACCION,
            "unidad_medida": "Documento",
            "meta_anual": "1",
            "area_ejecutora_id": area,
        },
    )
    assert actividad.status_code == 201, actividad.text
    return {**cedula, "actividad_id": actividad.json()["id"]}


async def _dos_tarjetas_en_dos_poas(app, client, headers, *, area: int) -> dict[int, dict]:
    """Dos cédulas de dos POAs distintos, cada una con su acción `1.1.1` ya
    seguida, y lo que la tarjeta de cada una tiene que decir.

    Devuelve `{cedula_id: {"seguimiento": id, "descripcion": texto}}`. El
    escenario lo piden las dos lecturas del seguimiento -el listado del tablero
    y la tarjeta suelta de la captura del avance-, que resuelven la descripción
    por su cuenta y por eso se miden por separado: cada una tiene que poder
    morir sola. Las dos tarjetas comparten área ejecutora, así que el filtro por
    área del tablero las trae a las dos y a nada más.
    """
    repositorio = app.state.poa_form_repository
    sembradas: dict[int, dict] = {}
    for texto in ("del POA de esta tarjeta", "del otro POA"):
        _, ejercicio = await _poa_con_su_ejercicio(client, headers, texto=texto)
        cedula = await _cedula_con_su_accion(client, headers, ejercicio=ejercicio, area=area)
        seguimiento = await repositorio.upsert_follow_up(
            PoaActivityFollowUp.create(
                form_activity_id=cedula["actividad_id"],
                quarter=1,
                period_id=cedula["cuatrimestres"][0]["periodo_id"],
                captured_by=cedula["creado_por"],
                scheduled=Decimal(1),
            )
        )
        sembradas[cedula["id"]] = {
            "seguimiento": seguimiento.id,
            "descripcion": f"La acción {_ACCION} {texto}",
        }
    return sembradas


def _unico_bloque_escrito(libro):
    """La hoja y el bloque donde quedó la única cédula del archivo exportado.

    No se busca por la denominación -como hace `_bloque_de` de
    `tests/test_formato_sep.py`- porque aquí la denominación es justo lo que se
    está comprobando: localizar el bloque por ella daría por bueno lo que falta
    por mirar. Se busca por «el único bloque que no quedó en blanco», que
    `limpiar_bloque` hace posible al vaciar todos antes de escribir.
    """
    escritos = [
        (libro[bloque.hoja], bloque)
        for bloque in localizar_bloques(libro)
        if libro[bloque.hoja].cell(row=bloque.estrategia + 2, column=2).value
    ]
    assert len(escritos) == 1, [bloque.hoja for _, bloque in escritos]
    return escritos[0]


@pytest.mark.asyncio
async def test_editar_el_poa_nuevo_no_toca_la_cedula_vieja(backend_client, planeacion_headers):
    """Comprobado en vivo antes de esta entrega: hoy el texto de la cédula
    vieja cambia solo. Después de esto, no.

    Cubre las cuatro consultas de `_detail_response`, que es por donde la
    pantalla de la cédula lee los nombres.
    """
    app, client = backend_client

    # El POA y la cédula del año viejo.
    _, ejercicio_viejo = await _poa_con_su_ejercicio(
        client, planeacion_headers, texto="como se escribió en el POA viejo"
    )
    creada = await _crear_cedula(
        client,
        planeacion_headers,
        ejercicio=ejercicio_viejo["id"],
        anio=ejercicio_viejo["anio"],
        area=await _area(app),
        clave=_ESTRATEGIA,
    )
    assert creada.status_code == 201, creada.text
    cedula = creada.json()["id"]

    # Un POA nuevo con su propia 1.1, y se edita ahí.
    nuevo, _ = await _poa_con_su_ejercicio(client, planeacion_headers, texto="del POA nuevo")
    editado = await client.patch(
        f"{API}/poa/catalogos/estrategias/{_ESTRATEGIA}",
        headers=planeacion_headers,
        params={"catalogo_id": nuevo["id"]},
        json={
            "objetivo_numero": _OBJETIVO,
            "denominacion": "TEXTO NUEVO DEL POA NUEVO",
            "activo": True,
        },
    )
    assert editado.status_code == 200, editado.text

    detalle = await client.get(f"{API}/poa/cedulas/{cedula}", headers=planeacion_headers)

    assert detalle.status_code == 200, detalle.text
    cuerpo = detalle.json()
    assert cuerpo["estrategia_denominacion"] == f"La {_ESTRATEGIA} como se escribió en el POA viejo"
    # El objetivo sale de la misma resolución, y el POA sembrado también tiene
    # un objetivo 1: si se resolviera allá, este texto sería el de la SEP.
    assert cuerpo["objetivo_denominacion"] == "El objetivo como se escribió en el POA viejo"


@pytest.mark.asyncio
async def test_el_tablero_resuelve_cada_tarjeta_en_el_poa_de_su_cedula(
    backend_client, planeacion_headers
):
    """El tablero abarca varios ejercicios -`ejercicio_id` es opcional- y pide
    el catálogo de acciones fuera del bucle de tarjetas para no caer en N+1.

    Con dos POAs a la vista, resolver «de una vez» ya no puede significar «con
    un solo catálogo»: cada tarjeta tiene que leer la descripción del POA de su
    propia cédula. Las dos tarjetas usan la acción `1.1.1` y comparten área
    ejecutora, así que el filtro por área las trae a las dos y a nada más.
    """
    app, client = backend_client
    area = await _area(app)
    sembradas = await _dos_tarjetas_en_dos_poas(app, client, planeacion_headers, area=area)
    esperado = {cedula: datos["descripcion"] for cedula, datos in sembradas.items()}

    tablero = await client.get(
        f"{API}/poa/seguimientos", headers=planeacion_headers, params={"area_id": area}
    )

    assert tablero.status_code == 200, tablero.text
    tarjetas = tablero.json()["items"]
    assert len(tarjetas) == 2, tarjetas
    assert {
        tarjeta["cedula_id"]: tarjeta["actividad"]["descripcion"] for tarjeta in tarjetas
    } == esperado


@pytest.mark.asyncio
async def test_el_reporte_resuelve_cada_cedula_en_el_poa_de_la_suya(
    backend_client, planeacion_headers
):
    """El servicio de reportes abarca varios ejercicios por el mismo motivo que
    el tablero, y carga el catálogo antes del bucle de cédulas.

    La suite no podía cazar esto: todos sus datos de prueba viven en un solo
    POA, así que resolver bien y resolver mal dan lo mismo. Aquí hay dos.
    """
    app, client = backend_client
    area = await _area(app)

    esperado = set()
    for texto in ("del POA de esta cédula", "del otro POA"):
        _, ejercicio = await _poa_con_su_ejercicio(client, planeacion_headers, texto=texto)
        cedula = await _cedula_con_su_accion(
            client, planeacion_headers, ejercicio=ejercicio, area=area
        )
        esperado.add((cedula["id"], f"La acción {_ACCION} {texto}"))

    # Sin `ejercicio_id`: es el caso que obliga a resolver por POA. El filtro
    # por área deja fuera las cédulas de las demás pruebas, que en PostgreSQL
    # sobreviven en la base durante toda la corrida.
    reporte = await client.get(
        f"{API}/poa/reportes/cuatrimestral", headers=planeacion_headers, params={"area_id": area}
    )

    assert reporte.status_code == 200, reporte.text
    filas = reporte.json()["filas"]
    assert filas, reporte.text
    assert {(fila["cedula_id"], fila["descripcion"]) for fila in filas} == esperado


@pytest.mark.asyncio
async def test_la_tarjeta_suelta_resuelve_su_descripcion_en_el_poa_de_su_cedula(
    backend_client, planeacion_headers
):
    """`GET /poa/seguimientos/{id}` es la pantalla donde un área captura su
    avance cuatrimestral, y tiene URL propia: «tiene que poder cargarse sola,
    sin haber pasado antes por el tablero», dice la propia función.

    Se arma con el mismo `_tarjeta_respuesta` que el listado, pero resuelve la
    descripción por su cuenta -`get_activity_catalog(activity.catalog_id, …)`-,
    así que la prueba del tablero no la toca. Con el POA equivocado hay dos
    salidas y las dos son malas: si el otro POA no tiene la clave se muestra la
    clave desnuda en vez de la descripción, y si la tiene con otro texto se
    muestra la acción de otro año sin que nada lo diga.

    Las dos tarjetas se piden una por una y se comparan contra la pareja
    completa: así una regla de «un solo catálogo para todas» falla en al menos
    una, sea el primer POA, el último o cualquier otro fijo.
    """
    app, client = backend_client
    area = await _area(app)
    sembradas = await _dos_tarjetas_en_dos_poas(app, client, planeacion_headers, area=area)

    descripciones = {}
    for cedula, datos in sembradas.items():
        tarjeta = await client.get(
            f"{API}/poa/seguimientos/{datos['seguimiento']}", headers=planeacion_headers
        )
        assert tarjeta.status_code == 200, tarjeta.text
        cuerpo = tarjeta.json()
        # Que la tarjeta pedida es la de esta cédula, y no otra: sin esto la
        # comparación de abajo podría cuadrar por casualidad.
        assert cuerpo["cedula_id"] == cedula, cuerpo
        descripciones[cedula] = cuerpo["actividad"]["descripcion"]

    assert descripciones == {cedula: datos["descripcion"] for cedula, datos in sembradas.items()}


@pytest.mark.asyncio
async def test_el_formato_de_la_sep_lleva_los_nombres_del_poa_de_su_ejercicio(
    backend_client, planeacion_headers
):
    """El `.xlsm` que se entrega a Rectoría y a la SEP, el peor sitio posible
    para este defecto: el archivo sale del sistema y nadie puede compararlo con
    nada.

    Lo que no cubría nada hasta aquí. `tests/test_formato_sep.py` ejercita
    `llenar_formato` sobre `CedulaDelFormato` armadas a mano -el relleno del
    Excel está bien probado- y nunca llama a `ExportarFormatoSep.execute()`, que
    es quien decide de qué POA salen los nombres; y
    `tests/test_reportes_poa.py` pide el endpoint sobre un ejercicio **sin
    cédulas**, así que el bucle donde vive la resolución no corre ni una vez.

    El ejercicio que se exporta es el del **primero de los dos POAs que crea
    esta prueba**, elegido así para que las reglas equivocadas no acierten por
    casualidad: no es el primer POA del sistema -el sembrado va antes y tiene su
    propia `1.1`, con el texto de la SEP-, ni el último, ni el más reciente, ni
    el del año más alto -`anio_libre` reparte de abajo arriba, así que el
    segundo POA se lleva el año mayor-, ni el del año más bajo -ése es el
    sembrado, 2026-, ni el del id más alto o más bajo. Las siete reglas
    devuelven un texto distinto del que se afirma; la única que acierta es
    «resuelve en el POA del que cuelga el ejercicio».
    """
    app, client = backend_client
    area = await _area(app)
    texto = "del POA que se exporta"

    _, ejercicio = await _poa_con_su_ejercicio(client, planeacion_headers, texto=texto)
    cedula = await _cedula_con_su_accion(
        client, planeacion_headers, ejercicio=ejercicio, area=area
    )
    # El indicador se cuelga aquí y no en `_cedula_con_su_accion` porque sólo
    # esta prueba lo mira: es la cuarta consulta al catálogo del exportador, y
    # las otras dos pruebas que usan ese ayudante no leen indicadores.
    indicador = await client.post(
        f"{API}/poa/cedulas/{cedula['id']}/indicadores",
        headers=planeacion_headers,
        json={"indicador_clave": _INDICADOR},
    )
    assert indicador.status_code == 201, indicador.text
    # El segundo POA existe para que el que se exporta no sea ni el último, ni
    # el más reciente, ni el del año mayor. No le hace falta cédula: lo que se
    # resuelve contra un POA es el catálogo, y éste ya trae el suyo.
    await _poa_con_su_ejercicio(client, planeacion_headers, texto="del POA de después")

    descarga = await client.get(
        f"{API}/poa/reportes/formato-sep",
        headers=planeacion_headers,
        params={"ejercicio_id": ejercicio["id"]},
    )

    assert descarga.status_code == 200, descarga.text[:200]
    hoja, bloque = _unico_bloque_escrito(load_workbook(BytesIO(descarga.content), keep_vba=True))
    # Las **cuatro** consultas que el exportador hace al catálogo: la
    # denominación de la estrategia (`get_strategy`), la del objetivo
    # (`list_objectives`), la descripción de la acción
    # (`list_activity_catalog`) y el nombre del indicador (`list_indicators`).
    # Las cuatro salen de la misma local de `sep_export.py`, así que basta una
    # para cazar al mutante; van las cuatro porque son cuatro consultas
    # distintas y cada una puede desviarse sola.
    assert hoja.cell(row=bloque.estrategia + 2, column=2).value == f"La {_ESTRATEGIA} {texto}"
    assert hoja.cell(row=bloque.objetivo, column=3).value == f"El objetivo {texto}"
    # `con_clave` antepone la clave cuando el texto no la trae ya.
    assert (
        hoja.cell(row=bloque.actividades_desde, column=2).value
        == f"{_ACCION} La acción {_ACCION} {texto}"
    )
    assert (
        hoja.cell(row=bloque.indicadores[0] + 1, column=2).value
        == f"{_INDICADOR} El indicador {_INDICADOR} {texto}"
    )
