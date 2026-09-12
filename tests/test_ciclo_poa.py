"""Ciclo del ejercicio POA: estados y fecha limite de formulacion.

Hasta ahora el ejercicio nacia como `{id, anio}` sin saber en que punto del
ciclo estaba. Planeacion arma el ejercicio y lo manda a Rectoria; Rectoria lo
aprueba (entra en vigor) o lo devuelve con un motivo (vuelve a borrador); al
terminar el ano, Planeacion lo cierra.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.modules.identity_access.application.dto import RegisterUserCommand
from app.modules.identity_access.application.use_cases.create_user import CreateUser
from app.modules.identity_access.domain.value_objects import Role
from app.modules.poa_planning.application.use_cases.manage_exercise import (
    ApproveExercise,
    ExerciseActionCommand,
    RejectExercise,
)
from app.modules.poa_planning.domain.entities import PoaExercise
from app.shared.application.actor import ActorContext
from app.shared.domain.exceptions import ForbiddenError, InvalidStateError
from app.shared.infrastructure.db.sql_loader import split_sql


def _random_year() -> int:
    # El anio es unico en poa_ejercicios y la base de pruebas persiste entre
    # corridas: se genera al azar en vez de usar un valor fijo.
    return 2000 + (uuid4().int % 200)


async def _account(app, client, role: Role, suffix: str, area_id: int | None = None):
    email = f"ciclo-poa-{role.value}-{suffix}@example.com"
    user = await CreateUser(
        app.state.user_repository, app.state.password_hasher, app.state.event_bus
    ).execute(
        RegisterUserCommand(
            email=email,
            full_name=f"Ciclo POA {role.value}",
            password="password-seguro",
            roles={role},
            area_id=area_id,
        )
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"correo": email, "contrasena": "password-seguro"},
    )
    assert login.status_code == 200, login.text
    return user, {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _new_exercise(client, headers, *, with_deadline: bool = False) -> dict:
    for _ in range(8):
        anio = _random_year()
        body = {"anio": anio}
        if with_deadline:
            body["fecha_limite_formulacion"] = f"{anio}-02-20"
        response = await client.post("/api/v1/poa/ejercicios", headers=headers, json=body)
        if response.status_code == 201:
            return response.json()
        assert response.status_code == 409, response.text
    raise AssertionError("No se encontro un anio libre para el ejercicio POA de prueba.")


async def _scenario(app, client) -> dict:
    suffix = uuid4().hex[:8]
    _, admin_headers = await _account(app, client, Role.ADMIN_SISTEMA, suffix)
    _, rectoria_headers = await _account(app, client, Role.RECTORIA, suffix)

    ejercicio = await _new_exercise(client, admin_headers)

    area = await client.post(
        "/api/v1/catalogos/areas",
        headers=admin_headers,
        json={"codigo": f"CICLO-{suffix}", "nombre": f"Area ciclo POA {suffix}"},
    )
    assert area.status_code == 201, area.text

    return {
        "suffix": suffix,
        "admin_headers": admin_headers,
        "rectoria_headers": rectoria_headers,
        "exercise_id": ejercicio["id"],
        "anio": ejercicio["anio"],
        "area_id": area.json()["id"],
    }


async def _add_cedula(client, escenario) -> None:
    """Le da al ejercicio la cedula que `enviar` exige."""
    anio = escenario["anio"]
    form = await client.post(
        "/api/v1/poa/cedulas",
        headers=escenario["admin_headers"],
        json={
            "ejercicio_id": escenario["exercise_id"],
            "estrategia_clave": "6.1",
            "area_responsable_id": escenario["area_id"],
            "cuatrimestres": [
                {"numero": 1, "fecha_inicio": f"{anio}-01-01", "fecha_fin": f"{anio}-04-30"},
                {"numero": 2, "fecha_inicio": f"{anio}-05-01", "fecha_fin": f"{anio}-08-31"},
                {"numero": 3, "fecha_inicio": f"{anio}-09-01", "fecha_fin": f"{anio}-12-31"},
            ],
        },
    )
    assert form.status_code == 201, form.text


@pytest.mark.asyncio
async def test_ejercicio_nace_en_borrador_con_fecha_limite(backend_client):
    app, client = backend_client
    suffix = uuid4().hex[:8]
    _, admin_headers = await _account(app, client, Role.ADMIN_SISTEMA, suffix)

    creado = await _new_exercise(client, admin_headers, with_deadline=True)

    assert creado["estado"] == "borrador"
    assert creado["comentario_revision"] is None
    assert creado["fecha_limite_formulacion"] == f"{creado['anio']}-02-20"


@pytest.mark.asyncio
async def test_no_se_envia_sin_cedulas(backend_client):
    app, client = backend_client
    escenario = await _scenario(app, client)

    rechazado = await client.post(
        f"/api/v1/poa/ejercicios/{escenario['exercise_id']}/enviar",
        headers=escenario["admin_headers"],
    )
    assert rechazado.status_code == 422, rechazado.text
    assert "cédula" in rechazado.json()["message"].lower()

    await _add_cedula(client, escenario)

    listado = await client.get("/api/v1/poa/ejercicios", headers=escenario["admin_headers"])
    assert listado.status_code == 200, listado.text
    item = next(i for i in listado.json() if i["id"] == escenario["exercise_id"])
    assert item["total_cedulas"] == 1

    enviado = await client.post(
        f"/api/v1/poa/ejercicios/{escenario['exercise_id']}/enviar",
        headers=escenario["admin_headers"],
    )
    assert enviado.status_code == 200, enviado.text
    assert enviado.json()["estado"] == "enviado"


@pytest.mark.asyncio
async def test_solo_rectoria_aprueba_y_lo_deja_vigente(backend_client):
    app, client = backend_client
    escenario = await _scenario(app, client)
    await _add_cedula(client, escenario)
    _, planeacion_headers = await _account(app, client, Role.PLANEACION, escenario["suffix"])

    enviado = await client.post(
        f"/api/v1/poa/ejercicios/{escenario['exercise_id']}/enviar",
        headers=escenario["admin_headers"],
    )
    assert enviado.status_code == 200, enviado.text

    denegado_aprobar = await client.post(
        f"/api/v1/poa/ejercicios/{escenario['exercise_id']}/aprobar",
        headers=planeacion_headers,
    )
    assert denegado_aprobar.status_code == 403, denegado_aprobar.text

    denegado_devolver = await client.post(
        f"/api/v1/poa/ejercicios/{escenario['exercise_id']}/devolver",
        headers=planeacion_headers,
        json={"comentario": "Un motivo cualquiera"},
    )
    assert denegado_devolver.status_code == 403, denegado_devolver.text

    aprobado = await client.post(
        f"/api/v1/poa/ejercicios/{escenario['exercise_id']}/aprobar",
        headers=escenario["rectoria_headers"],
    )
    assert aprobado.status_code == 200, aprobado.text
    assert aprobado.json()["estado"] == "vigente"


@pytest.mark.asyncio
async def test_admin_sistema_y_planeacion_admin_no_aprueban_ni_devuelven(backend_client):
    # La aprobacion existe para que Planeacion no apruebe su propio trabajo.
    # `admin_sistema` queda fuera a proposito, y `planeacion_admin` tambien:
    # `require_roles` lo expande a `planeacion` + `admin_sistema`, asi que si
    # `admin_sistema` colara aqui, una cuenta de Planeacion terminaria
    # aprobando su propio ejercicio por la puerta de atras.
    app, client = backend_client
    escenario = await _scenario(app, client)
    await _add_cedula(client, escenario)
    _, planeacion_admin_headers = await _account(
        app, client, Role.PLANEACION_ADMIN, escenario["suffix"]
    )

    enviado = await client.post(
        f"/api/v1/poa/ejercicios/{escenario['exercise_id']}/enviar",
        headers=escenario["admin_headers"],
    )
    assert enviado.status_code == 200, enviado.text

    for etiqueta, headers in (
        ("admin_sistema", escenario["admin_headers"]),
        ("planeacion_admin", planeacion_admin_headers),
    ):
        denegado_aprobar = await client.post(
            f"/api/v1/poa/ejercicios/{escenario['exercise_id']}/aprobar",
            headers=headers,
        )
        assert denegado_aprobar.status_code == 403, (etiqueta, denegado_aprobar.text)

        denegado_devolver = await client.post(
            f"/api/v1/poa/ejercicios/{escenario['exercise_id']}/devolver",
            headers=headers,
            json={"comentario": "Un motivo cualquiera"},
        )
        assert denegado_devolver.status_code == 403, (etiqueta, denegado_devolver.text)

    # Rectoria, en cambio, si puede: el ejercicio sigue intacto (nadie lo
    # movio de "enviado" en los intentos denegados de arriba).
    aprobado = await client.post(
        f"/api/v1/poa/ejercicios/{escenario['exercise_id']}/aprobar",
        headers=escenario["rectoria_headers"],
    )
    assert aprobado.status_code == 200, aprobado.text
    assert aprobado.json()["estado"] == "vigente"


class _ColaboradorQueNoDeberiaTocarse:
    """Falla si algo lo invoca.

    `ApproveExercise`/`RejectExercise` deben rechazar por rol *antes* de tocar
    repositorio, cédulas, historial o bus de eventos. Si el chequeo de
    permisos se corriera o desapareciera, cualquiera de estos métodos se
    llamaría y la prueba fallaría por la razón equivocada (un error de
    `AssertionError` en vez de un `ForbiddenError`), delatando el problema.
    """

    def __getattr__(self, name: str):
        raise AssertionError(f"no debería llamarse a '{name}': el rol no aprueba")


@pytest.mark.asyncio
@pytest.mark.parametrize("rol_sin_permiso", ["admin_sistema", "planeacion_admin"])
@pytest.mark.parametrize("caso_de_uso", [ApproveExercise, RejectExercise])
async def test_admin_sistema_y_planeacion_admin_no_aprueban_ni_devuelven_en_el_caso_de_uso(
    caso_de_uso, rol_sin_permiso
):
    # Cubre la capa que la prueba HTTP de arriba no puede ver: el caso de uso
    # es el dueño real de la regla de negocio en arquitectura hexagonal, y
    # antes tenia su propia copia -mas permisiva- de APPROVAL_ROLES: el mismo
    # atajo que se suponia ya quitado del router. Si alguien vuelve a
    # bifurcar la constante, esta prueba revienta sin pasar por HTTP, que es
    # justo el camino que dejaba pasar el hueco desapercibido.
    colaborador = _ColaboradorQueNoDeberiaTocarse()
    use_case = caso_de_uso(colaborador, colaborador, colaborador, colaborador)
    actor = ActorContext(id=1, roles=frozenset({rol_sin_permiso}), area_id=None)
    comando = ExerciseActionCommand(exercise_id=1, actor=actor, comment="Un motivo cualquiera")

    with pytest.raises(ForbiddenError):
        await use_case.execute(comando)


@pytest.mark.asyncio
async def test_devolver_exige_comentario_y_regresa_a_borrador(backend_client):
    app, client = backend_client
    escenario = await _scenario(app, client)
    await _add_cedula(client, escenario)
    await client.post(
        f"/api/v1/poa/ejercicios/{escenario['exercise_id']}/enviar",
        headers=escenario["admin_headers"],
    )

    sin_motivo = await client.post(
        f"/api/v1/poa/ejercicios/{escenario['exercise_id']}/devolver",
        headers=escenario["rectoria_headers"],
        json={"comentario": "   "},
    )
    assert sin_motivo.status_code == 422, sin_motivo.text

    devuelto = await client.post(
        f"/api/v1/poa/ejercicios/{escenario['exercise_id']}/devolver",
        headers=escenario["rectoria_headers"],
        json={"comentario": "Falta desglosar el cuatrimestre 3."},
    )
    assert devuelto.status_code == 200, devuelto.text
    body = devuelto.json()
    assert body["estado"] == "borrador"
    assert body["comentario_revision"] == "Falta desglosar el cuatrimestre 3."

    # Vuelve a ser de Planeacion: puede reenviar sin que el motivo lo bloquee.
    reenviado = await client.post(
        f"/api/v1/poa/ejercicios/{escenario['exercise_id']}/enviar",
        headers=escenario["admin_headers"],
    )
    assert reenviado.status_code == 200, reenviado.text
    assert reenviado.json()["estado"] == "enviado"


@pytest.mark.asyncio
async def test_cerrar_solo_procede_desde_vigente(backend_client):
    app, client = backend_client
    escenario = await _scenario(app, client)
    await _add_cedula(client, escenario)

    bloqueado = await client.post(
        f"/api/v1/poa/ejercicios/{escenario['exercise_id']}/cerrar",
        headers=escenario["admin_headers"],
    )
    assert bloqueado.status_code == 422, bloqueado.text

    await client.post(
        f"/api/v1/poa/ejercicios/{escenario['exercise_id']}/enviar",
        headers=escenario["admin_headers"],
    )
    await client.post(
        f"/api/v1/poa/ejercicios/{escenario['exercise_id']}/aprobar",
        headers=escenario["rectoria_headers"],
    )

    cerrado = await client.post(
        f"/api/v1/poa/ejercicios/{escenario['exercise_id']}/cerrar",
        headers=escenario["admin_headers"],
    )
    assert cerrado.status_code == 200, cerrado.text
    assert cerrado.json()["estado"] == "cerrado"

    doble_cierre = await client.post(
        f"/api/v1/poa/ejercicios/{escenario['exercise_id']}/cerrar",
        headers=escenario["admin_headers"],
    )
    assert doble_cierre.status_code == 422, doble_cierre.text


@pytest.mark.asyncio
async def test_historial_queda_en_cambios_estado_con_entidad_poa_ejercicio(backend_client):
    # El ejercicio no reutiliza el vocabulario de la captura (`CaptureStatus`):
    # "vigente" y "cerrado" son estados propios de `PoaExerciseStatus`. Si la
    # lectura del historial siguiera asumiendo siempre `CaptureStatus`, leer de
    # vuelta la fila que deja `aprobar` o `cerrar` lanzaria
    # `ValueError: 'vigente' is not a valid CaptureStatus`. Por eso esta prueba
    # no se detiene en `enviar` (borrador -> enviado son validos en ambos
    # vocabularios y no habrian detectado el bug).
    app, client = backend_client
    escenario = await _scenario(app, client)
    await _add_cedula(client, escenario)

    enviado = await client.post(
        f"/api/v1/poa/ejercicios/{escenario['exercise_id']}/enviar",
        headers=escenario["admin_headers"],
    )
    assert enviado.status_code == 200, enviado.text

    aprobado = await client.post(
        f"/api/v1/poa/ejercicios/{escenario['exercise_id']}/aprobar",
        headers=escenario["rectoria_headers"],
    )
    assert aprobado.status_code == 200, aprobado.text

    cerrado = await client.post(
        f"/api/v1/poa/ejercicios/{escenario['exercise_id']}/cerrar",
        headers=escenario["admin_headers"],
    )
    assert cerrado.status_code == 200, cerrado.text

    # El ejercicio recien creado tiene un id nuevo: el historial de este
    # entity_id no puede traer nada de corridas anteriores de la suite.
    historial, total = await app.state.state_change_repository.list_for_capture_page(
        escenario["exercise_id"],
        offset=0,
        limit=10,
        descending=False,
        entity="poa_ejercicio",
    )
    assert total == 3
    assert [cambio.entity for cambio in historial] == ["poa_ejercicio"] * 3
    assert [cambio.entity_id for cambio in historial] == [escenario["exercise_id"]] * 3
    assert historial[0].from_status.value == "borrador"
    assert historial[0].to_status.value == "enviado"
    assert historial[1].from_status.value == "enviado"
    assert historial[1].to_status.value == "vigente"
    assert historial[2].from_status.value == "vigente"
    assert historial[2].to_status.value == "cerrado"


def test_ensure_editable_bloquea_fuera_de_borrador_o_tras_la_fecha_limite():
    activo = PoaExercise.create(2199, formulation_deadline=date(2199, 2, 20))
    activo.ensure_editable(date(2199, 2, 19))  # no debe lanzar: sigue en borrador y a tiempo

    with pytest.raises(InvalidStateError):
        activo.ensure_editable(date(2199, 2, 21))  # ya paso la fecha limite

    enviado = PoaExercise.create(2198)
    enviado.send(has_forms=True)
    with pytest.raises(InvalidStateError):
        enviado.ensure_editable(date(2198, 1, 1))  # ya no esta en borrador


# ---------------------------------------------------------------------------
# Tarea 2: la actividad gana su explicacion UPE y sus criterios SEAES, que
# ahora son varios por actividad en vez de uno solo (migracion 0031).
# ---------------------------------------------------------------------------


async def _new_activity_scenario(app, client) -> dict:
    """Cedula con una actividad ya creada, lista para asignarle criterios o
    la explicacion UPE. Devuelve tambien un capturista del area ejecutora,
    para comprobar que ve lo que Planeacion escribe."""
    suffix = uuid4().hex[:8]
    _, admin_headers = await _account(app, client, Role.ADMIN_SISTEMA, suffix)
    ejercicio = await _new_exercise(client, admin_headers)
    anio = ejercicio["anio"]

    area = await client.post(
        "/api/v1/catalogos/areas",
        headers=admin_headers,
        json={"codigo": f"UPE-{suffix}", "nombre": f"Area UPE {suffix}"},
    )
    assert area.status_code == 201, area.text
    area_id = area.json()["id"]
    _, capturer_headers = await _account(app, client, Role.CAPTURISTA_POA, suffix, area_id)

    form = await client.post(
        "/api/v1/poa/cedulas",
        headers=admin_headers,
        json={
            "ejercicio_id": ejercicio["id"],
            "estrategia_clave": "6.1",
            "area_responsable_id": area_id,
            "cuatrimestres": [
                {"numero": 1, "fecha_inicio": f"{anio}-01-01", "fecha_fin": f"{anio}-04-30"},
                {"numero": 2, "fecha_inicio": f"{anio}-05-01", "fecha_fin": f"{anio}-08-31"},
                {"numero": 3, "fecha_inicio": f"{anio}-09-01", "fecha_fin": f"{anio}-12-31"},
            ],
        },
    )
    assert form.status_code == 201, form.text
    form_id = form.json()["id"]

    activity = await client.post(
        f"/api/v1/poa/cedulas/{form_id}/actividades",
        headers=admin_headers,
        json={
            "actividad_clave": "6.1.1",
            "unidad_medida": "Eventos",
            "meta_anual": 100,
            "area_ejecutora_id": area_id,
        },
    )
    assert activity.status_code == 201, activity.text

    return {
        "admin_headers": admin_headers,
        "capturer_headers": capturer_headers,
        "form_id": form_id,
        "activity_id": activity.json()["id"],
    }


async def _new_criterio(client, admin_headers) -> int:
    suffix = uuid4().hex[:8]
    response = await client.post(
        "/api/v1/catalogos/criterios-seaes",
        headers=admin_headers,
        json={"clave": f"C-{suffix}", "nombre": f"Criterio {suffix}"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.mark.asyncio
async def test_asignar_dos_criterios_los_devuelve_en_orden_estable(backend_client):
    app, client = backend_client
    escenario = await _new_activity_scenario(app, client)
    criterio_a = await _new_criterio(client, escenario["admin_headers"])
    criterio_b = await _new_criterio(client, escenario["admin_headers"])
    esperado = sorted([criterio_a, criterio_b])

    # Se mandan en orden inverso al esperado para que la prueba ejercite el
    # orden estable de la respuesta y no una coincidencia con el orden de
    # entrada.
    asignado = await client.patch(
        f"/api/v1/poa/cedulas/actividades/{escenario['activity_id']}/criterios-seaes",
        headers=escenario["admin_headers"],
        json={"criterio_seaes_ids": [max(criterio_a, criterio_b), min(criterio_a, criterio_b)]},
    )
    assert asignado.status_code == 200, asignado.text
    assert asignado.json()["criterio_seaes_ids"] == esperado

    # El orden se sostiene tambien al releer la cedula completa, no solo en
    # la respuesta inmediata de la asignacion.
    consulta = await client.get(
        f"/api/v1/poa/cedulas/{escenario['form_id']}", headers=escenario["admin_headers"]
    )
    assert consulta.status_code == 200, consulta.text
    actividad = next(
        a for a in consulta.json()["actividades"] if a["id"] == escenario["activity_id"]
    )
    assert actividad["criterio_seaes_ids"] == esperado


@pytest.mark.asyncio
async def test_asignar_lista_vacia_quita_todos_los_criterios(backend_client):
    app, client = backend_client
    escenario = await _new_activity_scenario(app, client)
    criterio = await _new_criterio(client, escenario["admin_headers"])

    asignado = await client.patch(
        f"/api/v1/poa/cedulas/actividades/{escenario['activity_id']}/criterios-seaes",
        headers=escenario["admin_headers"],
        json={"criterio_seaes_ids": [criterio]},
    )
    assert asignado.status_code == 200, asignado.text
    assert asignado.json()["criterio_seaes_ids"] == [criterio]

    vaciado = await client.patch(
        f"/api/v1/poa/cedulas/actividades/{escenario['activity_id']}/criterios-seaes",
        headers=escenario["admin_headers"],
        json={"criterio_seaes_ids": []},
    )
    assert vaciado.status_code == 200, vaciado.text
    assert vaciado.json()["criterio_seaes_ids"] == []


@pytest.mark.asyncio
async def test_un_criterio_inexistente_en_la_lista_responde_404_nombrandolo(backend_client):
    app, client = backend_client
    escenario = await _new_activity_scenario(app, client)
    criterio = await _new_criterio(client, escenario["admin_headers"])
    inexistente = 999999999

    fallido = await client.patch(
        f"/api/v1/poa/cedulas/actividades/{escenario['activity_id']}/criterios-seaes",
        headers=escenario["admin_headers"],
        json={"criterio_seaes_ids": [criterio, inexistente]},
    )
    assert fallido.status_code == 404, fallido.text
    assert str(inexistente) in fallido.json()["message"]


@pytest.mark.asyncio
async def test_asignar_criterios_a_actividad_de_otra_area_responde_403(backend_client):
    # La restriccion central del proyecto: un area nunca toca datos de otra.
    # `_new_activity_scenario` crea la actividad en el area ejecutora "A" y
    # un capturista atado a esa misma area; aqui se crea una segunda area "B"
    # con su propio capturista, que no tiene por que poder clasificar una
    # actividad que no es suya. Si `can_capture_activity` dejara de filtrar
    # por area (o el router dejara de invocarlo), esto pasaria de 403 a 200.
    app, client = backend_client
    escenario = await _new_activity_scenario(app, client)
    criterio = await _new_criterio(client, escenario["admin_headers"])

    otra_area = await client.post(
        "/api/v1/catalogos/areas",
        headers=escenario["admin_headers"],
        json={
            "codigo": f"OTRA-{uuid4().hex[:8]}",
            "nombre": f"Otra area ejecutora {uuid4().hex[:8]}",
        },
    )
    assert otra_area.status_code == 201, otra_area.text
    _, capturista_de_otra_area = await _account(
        app, client, Role.CAPTURISTA_POA, uuid4().hex[:8], otra_area.json()["id"]
    )

    denegado = await client.patch(
        f"/api/v1/poa/cedulas/actividades/{escenario['activity_id']}/criterios-seaes",
        headers=capturista_de_otra_area,
        json={"criterio_seaes_ids": [criterio]},
    )
    assert denegado.status_code == 403, denegado.text


@pytest.mark.asyncio
async def test_asignar_criterios_con_ids_repetidos_los_deduplica(backend_client):
    # El comando reemplaza el conjunto completo de criterios; la unica dueña
    # de deduplicarlo y ordenarlo es la entidad (`PoaFormActivity.assign_
    # criteria`). El caso de uso y los repositorios (memoria y SQL) confian
    # en ese resultado sin volver a aplicar `sorted(set(...))` por su cuenta
    # -si lo hicieran, tapando una regresion en la entidad, esta prueba
    # pasaria en la variante "memory" aunque la deduplicacion real estuviera
    # rota-. En la variante "postgresql" la tabla muchos a muchos (llave
    # primaria compuesta) ademas fallaria al insertar la misma pareja dos
    # veces si algo mandara ids repetidos.
    app, client = backend_client
    escenario = await _new_activity_scenario(app, client)
    criterio = await _new_criterio(client, escenario["admin_headers"])

    asignado = await client.patch(
        f"/api/v1/poa/cedulas/actividades/{escenario['activity_id']}/criterios-seaes",
        headers=escenario["admin_headers"],
        json={"criterio_seaes_ids": [criterio, criterio, criterio]},
    )
    assert asignado.status_code == 200, asignado.text
    assert asignado.json()["criterio_seaes_ids"] == [criterio]


@pytest.mark.asyncio
async def test_la_explicacion_upe_se_guarda_y_el_area_ejecutora_la_ve(backend_client):
    app, client = backend_client
    escenario = await _new_activity_scenario(app, client)
    explicacion = "Para el area: dar mantenimiento preventivo a los 40 equipos del laboratorio."

    actualizado = await client.patch(
        f"/api/v1/poa/cedulas/actividades/{escenario['activity_id']}",
        headers=escenario["admin_headers"],
        json={"actividad_upe": explicacion},
    )
    assert actualizado.status_code == 200, actualizado.text
    assert actualizado.json()["actividad_upe"] == explicacion

    # El area ejecutora -no Planeacion- es quien la lee en el dia a dia.
    consulta = await client.get(
        f"/api/v1/poa/cedulas/{escenario['form_id']}", headers=escenario["capturer_headers"]
    )
    assert consulta.status_code == 200, consulta.text
    actividad = next(
        a for a in consulta.json()["actividades"] if a["id"] == escenario["activity_id"]
    )
    assert actividad["actividad_upe"] == explicacion


@pytest.mark.asyncio
async def test_migracion_0031_conserva_los_criterios_de_la_columna_singular():
    """La parte critica de la migracion 0031: copiar `criterio_seaes_id`
    antes de soltar la columna. Se ejecuta el .sql real -tal cual quedo en
    `bd/migrations`, sin reimplementarlo- sobre un esquema Postgres aislado
    que solo replica las piezas de las que depende (una actividad con
    criterio, otra sin el). La prueba falla si la migracion llega a perder
    el dato en vez de copiarlo antes del DROP COLUMN.
    """
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL no configurada")

    migration_sql = (
        Path(__file__).resolve().parents[1]
        / "bd"
        / "migrations"
        / "0031_actividad_upe_y_criterios.sql"
    ).read_text(encoding="utf-8")

    schema = f"migracion_0031_{uuid4().hex[:8]}"
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with engine.begin() as connection:
            await connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            await connection.exec_driver_sql(f'SET search_path TO "{schema}"')
            await connection.exec_driver_sql("CREATE TABLE criterios_seaes (id SERIAL PRIMARY KEY)")
            await connection.exec_driver_sql(
                "CREATE TABLE poa_cedula_actividades ("
                "id SERIAL PRIMARY KEY, criterio_seaes_id INTEGER REFERENCES criterios_seaes(id))"
            )
            await connection.exec_driver_sql(
                "CREATE INDEX idx_poa_cedula_actividades_criterio "
                "ON poa_cedula_actividades(criterio_seaes_id)"
            )
            criterio_id = await connection.scalar(
                text("INSERT INTO criterios_seaes DEFAULT VALUES RETURNING id")
            )
            con_criterio = await connection.scalar(
                text(
                    "INSERT INTO poa_cedula_actividades (criterio_seaes_id) "
                    "VALUES (:criterio) RETURNING id"
                ),
                {"criterio": criterio_id},
            )
            sin_criterio = await connection.scalar(
                text("INSERT INTO poa_cedula_actividades DEFAULT VALUES RETURNING id")
            )

            for statement in split_sql(migration_sql):
                await connection.exec_driver_sql(statement)

            migrado = (
                await connection.execute(
                    text(
                        "SELECT cedula_actividad_id, criterio_seaes_id "
                        "FROM poa_cedula_actividad_criterios "
                        "ORDER BY cedula_actividad_id"
                    )
                )
            ).all()
            assert [tuple(fila) for fila in migrado] == [(con_criterio, criterio_id)]
            assert sin_criterio not in [fila[0] for fila in migrado]

            columnas = (
                await connection.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = :schema AND table_name = 'poa_cedula_actividades'"
                    ),
                    {"schema": schema},
                )
            ).scalars().all()
            assert "criterio_seaes_id" not in columnas
            assert "actividad_upe" in columnas
    finally:
        async with engine.begin() as connection:
            await connection.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await engine.dispose()


# ---------------------------------------------------------------------------
# Tarea 3: catalogo de unidades de medida (migracion 0032). La unidad la
# define la institucion, no el PSE: la actividad sigue guardando su unidad
# como texto libre, el catalogo solo existe para ofrecerla y evitar que
# "Informe" e "Informes" convivan como si fueran cosas distintas.
# ---------------------------------------------------------------------------

_CLAVES_SEMBRADAS = {
    "porcentaje",
    "informe",
    "alumno",
    "curso",
    "documento",
    "estudiante",
    "evento",
    "profesor",
    "certificacion",
    "campana",
    "certificado",
    "convenio",
    "educando-alfabetizado",
    "equipo",
    "espacio",
    "mujer-atendida",
    "mujer-becada",
    "nodess-registrado",
    "personal",
    "proyecto",
}


@pytest.mark.asyncio
async def test_catalogo_unidades_medida_trae_las_veinte_sembradas(backend_client):
    app, client = backend_client
    _, headers = await _account(app, client, Role.ADMIN_SISTEMA, uuid4().hex[:8])

    respuesta = await client.get("/api/v1/catalogos/unidades-medida", headers=headers)
    assert respuesta.status_code == 200, respuesta.text
    unidades = respuesta.json()

    # La base de pruebas persiste entre corridas de este archivo: se
    # comprueba que las 20 sembradas por la migracion 0032 esten, no que
    # sean las unicas (esta suite tambien crea unidades con clave al azar).
    claves = {item["clave"] for item in unidades}
    assert _CLAVES_SEMBRADAS <= claves

    porcentaje = next(item for item in unidades if item["clave"] == "porcentaje")
    assert porcentaje["nombre"] == "Porcentaje"
    assert porcentaje["plural"] == "Porcentaje"
    assert porcentaje["activo"] is True

    informe = next(item for item in unidades if item["clave"] == "informe")
    assert informe["nombre"] == "Informe"
    assert informe["plural"] == "Informes"


@pytest.mark.asyncio
async def test_crear_y_desactivar_unidad_de_medida(backend_client):
    app, client = backend_client
    _, admin_headers = await _account(app, client, Role.ADMIN_SISTEMA, uuid4().hex[:8])
    # El anio y el correo del escenario no sirven de nada aqui: lo unico que
    # necesita ser unico es la clave, y la base de pruebas persiste.
    clave = f"prueba-{uuid4().hex[:8]}"

    creada = await client.post(
        "/api/v1/catalogos/unidades-medida",
        headers=admin_headers,
        json={"clave": clave, "nombre": "Unidad de prueba", "plural": "Unidades de prueba"},
    )
    assert creada.status_code == 201, creada.text
    cuerpo = creada.json()
    assert cuerpo["clave"] == clave
    assert cuerpo["nombre"] == "Unidad de prueba"
    assert cuerpo["plural"] == "Unidades de prueba"
    assert cuerpo["activo"] is True

    listado_activo = await client.get(
        "/api/v1/catalogos/unidades-medida",
        headers=admin_headers,
        params={"activo": "true"},
    )
    assert clave in {item["clave"] for item in listado_activo.json()}

    desactivada = await client.post(
        f"/api/v1/catalogos/unidades-medida/{cuerpo['id']}/desactivar",
        headers=admin_headers,
    )
    assert desactivada.status_code == 200, desactivada.text
    assert desactivada.json()["activo"] is False

    # El filtro ?activo=true (que tambien es el default) debe excluir la que
    # se acaba de desactivar.
    listado_tras_desactivar = await client.get(
        "/api/v1/catalogos/unidades-medida",
        headers=admin_headers,
        params={"activo": "true"},
    )
    assert clave not in {item["clave"] for item in listado_tras_desactivar.json()}

    # Pero sigue existiendo: se recupera pidiendo explicitamente las inactivas.
    listado_inactivo = await client.get(
        "/api/v1/catalogos/unidades-medida",
        headers=admin_headers,
        params={"activo": "false"},
    )
    assert clave in {item["clave"] for item in listado_inactivo.json()}
