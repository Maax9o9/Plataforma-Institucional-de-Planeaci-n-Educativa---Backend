"""Ningún consumidor del catálogo resuelve un nombre sin decir de qué POA.

Son las pruebas que resumen la entrega. El catálogo del POA era uno solo -la
clave `1.1` era llave primaria global-, así que corregir el texto de una
estrategia reescribía lo que mostraban las cédulas de todos los años.
Planeación lo dijo así: «lo que no quiero, que cambiando la información de las
cédulas, esto cambie la que contiene el 2026».

Las escrituras ya las ataja la base -las foráneas compuestas impiden que una
cédula, un indicador o una actividad cuelguen del catálogo de otro año-. Lo que
queda son las **lecturas que resuelven nombres**, y de ésas aquí están las tres
que nada cubría: el detalle de la cédula, el tablero de seguimiento y el
servicio de reportes. Las dos últimas son las difíciles, porque pueden abarcar
varios POAs a la vez: `ejercicio_id` es opcional en las dos. El formato de la
SEP resuelve nombres también, pero está acotado a un ejercicio y ya lo cubre
`test_formato_sep.py`.

Cada prueba crea **dos POAs con la misma clave y texto distinto**. Es lo único
que distingue «resolví en el POA de esta cédula» de «resolví en el primero que
encontré»: con el mismo texto en los dos, las dos implementaciones pasarían.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.poa_planning.domain.cedula_entities import PoaActivityFollowUp
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


async def _poa_con_catalogo(client, headers, *, anio: int, texto: str) -> dict:
    """Un POA nuevo con su objetivo, su estrategia y su acción propios.

    `texto` entra en las tres denominaciones y es lo que cada prueba compara:
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
    repositorio = app.state.poa_form_repository

    esperado = {}
    for texto in ("del POA de esta tarjeta", "del otro POA"):
        _, ejercicio = await _poa_con_su_ejercicio(client, planeacion_headers, texto=texto)
        cedula = await _cedula_con_su_accion(
            client, planeacion_headers, ejercicio=ejercicio, area=area
        )
        await repositorio.upsert_follow_up(
            PoaActivityFollowUp.create(
                form_activity_id=cedula["actividad_id"],
                quarter=1,
                period_id=cedula["cuatrimestres"][0]["periodo_id"],
                captured_by=cedula["creado_por"],
                scheduled=Decimal(1),
            )
        )
        esperado[cedula["id"]] = f"La acción {_ACCION} {texto}"

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
