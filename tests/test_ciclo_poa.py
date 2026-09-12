"""Ciclo del ejercicio POA: estados y fecha limite de formulacion.

Hasta ahora el ejercicio nacia como `{id, anio}` sin saber en que punto del
ciclo estaba. Planeacion arma el ejercicio y lo manda a Rectoria; Rectoria lo
aprueba (entra en vigor) o lo devuelve con un motivo (vuelve a borrador); al
terminar el ano, Planeacion lo cierra.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest

from app.modules.identity_access.application.dto import RegisterUserCommand
from app.modules.identity_access.application.use_cases.create_user import CreateUser
from app.modules.identity_access.domain.value_objects import Role
from app.modules.poa_planning.domain.entities import PoaExercise
from app.shared.domain.exceptions import InvalidStateError


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
    app, client = backend_client
    escenario = await _scenario(app, client)
    await _add_cedula(client, escenario)

    enviado = await client.post(
        f"/api/v1/poa/ejercicios/{escenario['exercise_id']}/enviar",
        headers=escenario["admin_headers"],
    )
    assert enviado.status_code == 200, enviado.text

    # El ejercicio recien creado tiene un id nuevo: el historial de este
    # entity_id no puede traer nada de corridas anteriores de la suite.
    historial, total = await app.state.state_change_repository.list_for_capture_page(
        escenario["exercise_id"],
        offset=0,
        limit=10,
        descending=False,
        entity="poa_ejercicio",
    )
    assert total == 1
    assert historial[0].entity == "poa_ejercicio"
    assert historial[0].entity_id == escenario["exercise_id"]
    assert historial[0].from_status.value == "borrador"
    assert historial[0].to_status.value == "enviado"


def test_ensure_editable_bloquea_fuera_de_borrador_o_tras_la_fecha_limite():
    activo = PoaExercise.create(2199, formulation_deadline=date(2199, 2, 20))
    activo.ensure_editable(date(2199, 2, 19))  # no debe lanzar: sigue en borrador y a tiempo

    with pytest.raises(InvalidStateError):
        activo.ensure_editable(date(2199, 2, 21))  # ya paso la fecha limite

    enviado = PoaExercise.create(2198)
    enviado.send(has_forms=True)
    with pytest.raises(InvalidStateError):
        enviado.ensure_editable(date(2198, 1, 1))  # ya no esta en borrador
