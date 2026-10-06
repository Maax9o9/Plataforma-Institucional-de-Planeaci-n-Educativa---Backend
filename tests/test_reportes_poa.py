"""Los reportes del POA se filtran por cuatrimestre, no sólo por periodo.

Cada cédula abre sus propios tres periodos, así que `periodo_id` identifica el
cuatrimestre *de una sola cédula*. La pregunta que trae a alguien a los
reportes —«cómo va el primer cuatrimestre del ejercicio»— no se podía
expresar: había que pedir un periodo por cédula y pegar los resultados a mano.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.modules.identity_access.application.dto import RegisterUserCommand
from app.modules.identity_access.application.use_cases.create_user import CreateUser
from app.modules.identity_access.domain.value_objects import Role

API = "/api/v1"


async def _admin(app, client, suffix: str) -> dict[str, str]:
    email = f"reportes-poa-{suffix}@example.com"
    await CreateUser(
        app.state.user_repository, app.state.password_hasher, app.state.event_bus
    ).execute(
        RegisterUserCommand(
            email=email,
            full_name="Reportes POA",
            password="password-seguro",
            roles={Role.ADMIN_SISTEMA},
            area_id=None,
        )
    )
    login = await client.post(
        f"{API}/auth/login", json={"correo": email, "contrasena": "password-seguro"}
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _primera_accion(client, headers, estrategia: str) -> str:
    catalogo = await client.get(
        f"{API}/poa/catalogos/actividades?estrategia_clave={estrategia}", headers=headers
    )
    assert catalogo.status_code == 200, catalogo.text
    acciones = catalogo.json()
    assert acciones, f"El catálogo no trae acciones de la estrategia {estrategia}."
    return acciones[0]["clave"]


async def _cedula_con_actividad(client, headers, *, ejercicio_id, anio, estrategia, area_id):
    cedula = await client.post(
        f"{API}/poa/cedulas",
        headers=headers,
        json={
            "ejercicio_id": ejercicio_id,
            "estrategia_clave": estrategia,
            "area_responsable_id": area_id,
            "cuatrimestres": [
                {"numero": 1, "fecha_inicio": f"{anio}-01-01", "fecha_fin": f"{anio}-04-30"},
                {"numero": 2, "fecha_inicio": f"{anio}-05-01", "fecha_fin": f"{anio}-08-31"},
                {"numero": 3, "fecha_inicio": f"{anio}-09-01", "fecha_fin": f"{anio}-12-31"},
            ],
        },
    )
    assert cedula.status_code == 201, cedula.text
    cuerpo = cedula.json()

    actividad = await client.post(
        f"{API}/poa/cedulas/{cuerpo['id']}/actividades",
        headers=headers,
        json={
            "actividad_clave": await _primera_accion(client, headers, estrategia),
            "unidad_medida": "Informe",
            "meta_anual": "3",
            "area_ejecutora_id": area_id,
        },
    )
    assert actividad.status_code == 201, actividad.text
    return {
        "id": cuerpo["id"],
        "cuatrimestres": {c["numero"]: c["periodo_id"] for c in cuerpo["cuatrimestres"]},
    }


@pytest.mark.asyncio
async def test_el_cuatrimestre_filtra_todo_el_ejercicio_y_el_periodo_una_sola_cedula(
    backend_client,
):
    app, client = backend_client
    suffix = uuid4().hex[:8]
    headers = await _admin(app, client, suffix)

    area = await client.post(
        f"{API}/catalogos/areas",
        headers=headers,
        json={"codigo": f"REP-{suffix}", "nombre": f"Área de reportes {suffix}"},
    )
    assert area.status_code == 201, area.text
    area_id = area.json()["id"]

    anio = 2000 + (uuid4().int % 200)
    for _ in range(8):
        ejercicio = await client.post(f"{API}/poa/ejercicios", headers=headers, json={"anio": anio})
        if ejercicio.status_code == 201:
            break
        assert ejercicio.status_code == 409, ejercicio.text
        anio = 2000 + (uuid4().int % 200)
    else:
        raise AssertionError("No se encontró un año libre para el ejercicio POA de prueba.")
    ejercicio_id = ejercicio.json()["id"]

    primera = await _cedula_con_actividad(
        client, headers, ejercicio_id=ejercicio_id, anio=anio, estrategia="1.1", area_id=area_id
    )
    segunda = await _cedula_con_actividad(
        client, headers, ejercicio_id=ejercicio_id, anio=anio, estrategia="1.3", area_id=area_id
    )

    # Dos cédulas, tres cuatrimestres cada una, una actividad cada una.
    completo = await client.get(
        f"{API}/poa/reportes/cuatrimestral?ejercicio_id={ejercicio_id}", headers=headers
    )
    assert completo.status_code == 200, completo.text
    assert len(completo.json()["filas"]) == 6

    # El periodo sólo alcanza a su propia cédula: es el límite que motivó el
    # filtro nuevo, y por eso se afirma además de lo que sí funciona.
    por_periodo = await client.get(
        f"{API}/poa/reportes/cuatrimestral"
        f"?ejercicio_id={ejercicio_id}&periodo_id={primera['cuatrimestres'][1]}",
        headers=headers,
    )
    assert {fila["cedula_id"] for fila in por_periodo.json()["filas"]} == {primera["id"]}

    # El cuatrimestre cruza las dos: es la pregunta que trae a esta pantalla.
    por_cuatrimestre = await client.get(
        f"{API}/poa/reportes/cuatrimestral?ejercicio_id={ejercicio_id}&cuatrimestre=1",
        headers=headers,
    )
    filas = por_cuatrimestre.json()["filas"]
    assert len(filas) == 2
    assert {fila["cedula_id"] for fila in filas} == {primera["id"], segunda["id"]}
    assert {fila["cuatrimestre"] for fila in filas} == {1}

    tercero = await client.get(
        f"{API}/poa/reportes/cuatrimestral?ejercicio_id={ejercicio_id}&cuatrimestre=3",
        headers=headers,
    )
    assert {fila["cuatrimestre"] for fila in tercero.json()["filas"]} == {3}


@pytest.mark.asyncio
async def test_un_cuatrimestre_que_no_existe_se_rechaza(backend_client):
    app, client = backend_client
    headers = await _admin(app, client, uuid4().hex[:8])

    fuera = await client.get(f"{API}/poa/reportes/cuatrimestral?cuatrimestre=4", headers=headers)

    assert fuera.status_code == 422, fuera.text
    assert "1, 2 o 3" in fuera.json()["message"]
