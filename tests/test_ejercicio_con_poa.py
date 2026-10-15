"""Un ejercicio no existe sin un POA del que colgar."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.identity_access.domain.value_objects import Role
from app.modules.poa_planning.domain.entities import PoaExercise
from app.shared.domain.exceptions import ConflictError, ValidationError
from helpers import (
    API,
    IDS_QUE_NO_PUEDEN_SER_DE_UN_POA,
    POA_INEXISTENTE,
    anio_libre,
    crear_ejercicio,
    crear_poa,
)
from test_ciclo_poa import _account


async def _enviado(app, ejercicio: dict) -> None:
    """Deja el ejercicio como Rectoría lo recibe.

    `enviar` exige al menos una cédula, y crear cédulas no es lo que se prueba
    aquí: se salta ese paso por el repositorio, con la misma transición de la
    entidad."""
    repositorio = app.state.poa_repository
    item = await repositorio.get_exercise(ejercicio["id"])
    item.send(has_forms=True)
    await repositorio.update_exercise(item)


@pytest.mark.asyncio
async def test_crear_un_ejercicio_sin_poa_se_rechaza(backend_client, planeacion_headers):
    """Sin POA el ejercicio no tiene estrategias que ofrecer al formular. El
    rechazo dice qué falta en vez de reventar con un error de base."""
    _, client = backend_client

    sin_poa = await client.post(
        f"{API}/poa/ejercicios", headers=planeacion_headers, json={"anio": 2031}
    )

    assert sin_poa.status_code == 422, sin_poa.text
    # Que sea 422 no basta: tiene que ser por *este* campo y no por otro.
    assert [(d["field"], d["type"]) for d in sin_poa.json()["details"]] == [
        ("catalogo_id", "missing")
    ]


@pytest.mark.asyncio
async def test_el_ejercicio_recuerda_su_poa(backend_client, planeacion_headers):
    app, client = backend_client
    anio = await anio_libre(client, planeacion_headers)
    poa = await crear_poa(client, planeacion_headers, anio)

    creado = await client.post(
        f"{API}/poa/ejercicios",
        headers=planeacion_headers,
        json={"anio": anio, "catalogo_id": poa["id"]},
    )

    assert creado.status_code == 201, creado.text
    assert creado.json()["catalogo_id"] == poa["id"]
    # Un id no se le muestra a nadie: la pantalla lee el nombre del POA, así que
    # tiene que venir en la respuesta y no resolverse allá.
    assert creado.json()["catalogo_nombre"] == poa["nombre"]
    # Y quedó guardado: quien lo lea después (la cédula, al resolver su POA)
    # tiene que encontrarlo en el ejercicio.
    guardado = await app.state.poa_repository.get_exercise(creado.json()["id"])
    assert guardado.catalog_id == poa["id"]


@pytest.mark.asyncio
async def test_el_listado_dice_de_que_poa_es_cada_ejercicio(backend_client, planeacion_headers):
    """Cada ejercicio trae el nombre de *su* POA, no el del primero ni el del
    inicial: con dos POA distintos, un nombre mal resuelto se nota."""
    _, client = backend_client
    primer_anio = await anio_libre(client, planeacion_headers)
    poa_a = await crear_poa(client, planeacion_headers, primer_anio)
    ejercicio_a = await crear_ejercicio(client, planeacion_headers, poa_a, primer_anio)
    segundo_anio = await anio_libre(client, planeacion_headers)
    poa_b = await crear_poa(client, planeacion_headers, segundo_anio)
    ejercicio_b = await crear_ejercicio(client, planeacion_headers, poa_b, segundo_anio)

    listado = await client.get(f"{API}/poa/ejercicios", headers=planeacion_headers)

    assert listado.status_code == 200, listado.text
    por_id = {ejercicio["id"]: ejercicio for ejercicio in listado.json()}
    assert por_id[ejercicio_a["id"]]["catalogo_id"] == poa_a["id"]
    assert por_id[ejercicio_a["id"]]["catalogo_nombre"] == poa_a["nombre"]
    assert por_id[ejercicio_b["id"]]["catalogo_id"] == poa_b["id"]
    assert por_id[ejercicio_b["id"]]["catalogo_nombre"] == poa_b["nombre"]


@pytest.mark.asyncio
async def test_cada_respuesta_del_ejercicio_dice_su_poa(backend_client, planeacion_headers):
    """Aprobar, devolver y cerrar contestan con el mismo esquema que la creación
    y el listado: la pantalla del ejercicio se repinta con esa respuesta, y si
    ahí el nombre del POA faltara, se apagaría justo después de actuar."""
    app, client = backend_client
    _, rectoria = await _account(app, client, Role.RECTORIA, uuid4().hex[:8])
    anio = await anio_libre(client, planeacion_headers)
    poa = await crear_poa(client, planeacion_headers, anio)
    vigente = await crear_ejercicio(client, planeacion_headers, poa, anio)
    devuelto = await crear_ejercicio(
        client, planeacion_headers, poa, await anio_libre(client, planeacion_headers)
    )
    await _enviado(app, vigente)
    await _enviado(app, devuelto)

    aprobado = await client.post(f"{API}/poa/ejercicios/{vigente['id']}/aprobar", headers=rectoria)
    cerrado = await client.post(
        f"{API}/poa/ejercicios/{vigente['id']}/cerrar", headers=planeacion_headers
    )
    regresado = await client.post(
        f"{API}/poa/ejercicios/{devuelto['id']}/devolver",
        headers=rectoria,
        json={"comentario": "Falta desglosar el cuatrimestre 3."},
    )

    for respuesta in (aprobado, cerrado, regresado):
        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.json()["catalogo_id"] == poa["id"]
        assert respuesta.json()["catalogo_nombre"] == poa["nombre"]


@pytest.mark.asyncio
async def test_un_poa_que_no_existe_no_da_ejercicio(backend_client, planeacion_headers):
    """404 con el POA nombrado, y nada creado: en memoria un id inventado dejaría
    un ejercicio colgando de la nada, y en PostgreSQL reventaría con la llave
    foránea cruda."""
    _, client = backend_client
    anio = await anio_libre(client, planeacion_headers)

    inexistente = await client.post(
        f"{API}/poa/ejercicios",
        headers=planeacion_headers,
        json={"anio": anio, "catalogo_id": POA_INEXISTENTE},
    )

    assert inexistente.status_code == 404, inexistente.text
    assert str(POA_INEXISTENTE) in inexistente.json()["message"]
    listado = await client.get(f"{API}/poa/ejercicios", headers=planeacion_headers)
    assert anio not in {ejercicio["anio"] for ejercicio in listado.json()}


@pytest.mark.asyncio
@pytest.mark.parametrize(("catalogo_id", "tipo"), IDS_QUE_NO_PUEDEN_SER_DE_UN_POA)
async def test_un_catalogo_id_que_no_puede_ser_de_un_poa_es_422(
    backend_client, planeacion_headers, catalogo_id, tipo
):
    """Un id que no cabe en el entero de 32 bits de la base no es «un POA que no
    existe»: PostgreSQL ni lo acepta como parámetro, y llegaría hasta allá para
    contestar 500 donde el contrato es 404. El cero tampoco es un POA que no
    existe: los ids son seriales y empiezan en 1."""
    _, client = backend_client
    anio = await anio_libre(client, planeacion_headers)

    rechazado = await client.post(
        f"{API}/poa/ejercicios",
        headers=planeacion_headers,
        json={"anio": anio, "catalogo_id": catalogo_id},
    )

    assert rechazado.status_code == 422, rechazado.text
    assert [(d["field"], d["type"]) for d in rechazado.json()["details"]] == [("catalogo_id", tipo)]


def test_la_entidad_no_depende_de_que_el_esquema_la_proteja():
    """`PoaExercise.create` valida por su cuenta: el esquema de entrada es una
    defensa, no la única."""
    with pytest.raises(ValidationError) as fallo:
        PoaExercise.create(2031, catalog_id=None)

    assert "POA" in str(fallo.value)


@pytest.mark.asyncio
async def test_dos_ejercicios_del_mismo_año_siguen_siendo_conflicto(
    backend_client, planeacion_headers
):
    """Escribir el POA no deshace la regla: un ejercicio por año **en todo el
    sistema**, por decisión del cliente, aunque cuelgue de otro POA. El segundo
    cuelga justamente de otro: con el mismo, relajar la única a
    `(anio, catalogo_id)` no se notaría. Se llama al repositorio directo,
    saltándose al caso de uso, para probar el adaptador y no sus comprobaciones."""
    app, client = backend_client
    anio = await anio_libre(client, planeacion_headers)
    primero = await crear_poa(client, planeacion_headers, anio)
    otro = await crear_poa(client, planeacion_headers, anio)
    repositorio = app.state.poa_repository
    await repositorio.add_exercise(PoaExercise.create(anio, catalog_id=primero["id"]))

    with pytest.raises(ConflictError):
        await repositorio.add_exercise(PoaExercise.create(anio, catalog_id=otro["id"]))


@pytest.mark.asyncio
@pytest.mark.parametrize("backend_client", ["postgresql"], indirect=True)
async def test_un_poa_inexistente_no_se_hace_pasar_por_año_repetido(
    backend_client, planeacion_headers
):
    """Sólo en PostgreSQL: la memoria no tiene llaves foráneas.

    Cualquier otra violación de restricción tiene que llegar tal cual. Decir «el
    ejercicio ya existe» cuando lo que falló fue la foránea al POA manda a quien
    depura a buscar un duplicado que no está, y es lo que hacía el `except` ancho
    con el `catalogo_id` que el adaptador no escribía."""
    app, client = backend_client
    anio = await anio_libre(client, planeacion_headers)

    with pytest.raises(IntegrityError) as fallo:
        await app.state.poa_repository.add_exercise(
            PoaExercise.create(anio, catalog_id=2_000_000_000)
        )

    assert "fk_poa_ejercicio_catalogo" in str(fallo.value)
