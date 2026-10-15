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
from helpers import poa_inicial_id

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
    # El catálogo se pide siempre de un POA: aquí, el que siembra el sistema.
    catalogo_id = await poa_inicial_id(client, headers)
    catalogo = await client.get(
        f"{API}/poa/catalogos/actividades?catalogo_id={catalogo_id}&estrategia_clave={estrategia}",
        headers=headers,
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

    catalogo_id = await poa_inicial_id(client, headers)
    anio = 2000 + (uuid4().int % 200)
    for _ in range(8):
        ejercicio = await client.post(
            f"{API}/poa/ejercicios",
            headers=headers,
            json={"anio": anio, "catalogo_id": catalogo_id},
        )
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


async def _rectoria(app, client, suffix: str) -> dict[str, str]:
    email = f"rectoria-reportes-{suffix}@example.com"
    await CreateUser(
        app.state.user_repository, app.state.password_hasher, app.state.event_bus
    ).execute(
        RegisterUserCommand(
            email=email,
            full_name="Rectoría",
            password="password-seguro",
            roles={Role.RECTORIA},
            area_id=None,
        )
    )
    login = await client.post(
        f"{API}/auth/login", json={"correo": email, "contrasena": "password-seguro"}
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_rectoria_lee_los_reportes_de_todas_las_areas(backend_client):
    """Rectoría valida el POA de la universidad: tiene que poder leerlo entero.

    El menú ya le ofrecía la sección y la ruta la dejaba entrar, pero cada
    consulta devolvía 403: veía una pantalla de error donde debía ver el POA.
    No se le abre la escritura —sigue sin poder tocar nada—, sólo la lectura
    sin filtro de área, que es la misma regla que ya gobierna el tablero.
    """
    app, client = backend_client
    suffix = uuid4().hex[:8]
    headers = await _admin(app, client, suffix)
    rectoria = await _rectoria(app, client, suffix)

    area = await client.post(
        f"{API}/catalogos/areas",
        headers=headers,
        json={"codigo": f"REC-{suffix}", "nombre": f"Área de rectoría {suffix}"},
    )
    assert area.status_code == 201, area.text

    catalogo_id = await poa_inicial_id(client, headers)
    anio = 2000 + (uuid4().int % 200)
    for _ in range(8):
        ejercicio = await client.post(
            f"{API}/poa/ejercicios",
            headers=headers,
            json={"anio": anio, "catalogo_id": catalogo_id},
        )
        if ejercicio.status_code == 201:
            break
        anio = 2000 + (uuid4().int % 200)
    else:
        raise AssertionError("No se encontró un año libre.")
    ejercicio_id = ejercicio.json()["id"]
    await _cedula_con_actividad(
        client,
        headers,
        ejercicio_id=ejercicio_id,
        anio=anio,
        estrategia="1.1",
        area_id=area.json()["id"],
    )

    reporte = await client.get(
        f"{API}/poa/reportes/cuatrimestral?ejercicio_id={ejercicio_id}", headers=rectoria
    )

    assert reporte.status_code == 200, reporte.text
    assert len(reporte.json()["filas"]) == 3
    # Y sin que se le fuerce el filtro de su área: Rectoría no tiene una.
    assert reporte.json()["filtros"]["area_id"] is None


@pytest.mark.asyncio
async def test_rectoria_descarga_el_formato_que_tiene_que_validar(backend_client):
    """Es el archivo que se le manda para dictaminar el POA. Negárselo
    obligaría a que Planeación se lo reenviara por correo, que es el trabajo
    paralelo que la plataforma viene a quitar."""
    app, client = backend_client
    suffix = uuid4().hex[:8]
    headers = await _admin(app, client, suffix)
    rectoria = await _rectoria(app, client, suffix)

    catalogo_id = await poa_inicial_id(client, headers)
    anio = 2000 + (uuid4().int % 200)
    for _ in range(8):
        ejercicio = await client.post(
            f"{API}/poa/ejercicios",
            headers=headers,
            json={"anio": anio, "catalogo_id": catalogo_id},
        )
        if ejercicio.status_code == 201:
            break
        anio = 2000 + (uuid4().int % 200)
    else:
        raise AssertionError("No se encontró un año libre.")

    descarga = await client.get(
        f"{API}/poa/reportes/formato-sep?ejercicio_id={ejercicio.json()['id']}", headers=rectoria
    )

    assert descarga.status_code == 200, descarga.text[:200]
    assert descarga.content.startswith(b"PK")


@pytest.mark.asyncio
async def test_un_area_sigue_viendo_solo_lo_suyo(backend_client):
    """Abrirle los reportes a Rectoría no puede abrírselos a todo el mundo: un
    capturista sigue viendo su área y nada más."""
    app, client = backend_client
    suffix = uuid4().hex[:8]
    headers = await _admin(app, client, suffix)

    area = await client.post(
        f"{API}/catalogos/areas",
        headers=headers,
        json={"codigo": f"CAP-{suffix}", "nombre": f"Área capturista {suffix}"},
    )
    assert area.status_code == 201, area.text
    email = f"capturista-reportes-{suffix}@example.com"
    await CreateUser(
        app.state.user_repository, app.state.password_hasher, app.state.event_bus
    ).execute(
        RegisterUserCommand(
            email=email,
            full_name="Capturista",
            password="password-seguro",
            roles={Role.CAPTURISTA_POA},
            area_id=area.json()["id"],
        )
    )
    login = await client.post(
        f"{API}/auth/login", json={"correo": email, "contrasena": "password-seguro"}
    )
    capturista = {"Authorization": f"Bearer {login.json()['access_token']}"}

    reporte = await client.get(f"{API}/poa/reportes/cuatrimestral", headers=capturista)

    assert reporte.status_code == 200, reporte.text
    assert reporte.json()["filtros"]["area_id"] == area.json()["id"]


@pytest.mark.asyncio
async def test_planeacion_filtra_por_el_area_que_pide(backend_client):
    """Quien ve todas las áreas tiene que poder quedarse con una.

    Es la otra mitad de la regla: a Rectoría y a Planeación no se les fuerza su
    área —no tienen una, o la suya no limita lo que revisan—, pero el filtro
    que piden sí manda. Sin esta prueba, ignorarlo pasaría desapercibido:
    quien ve todo seguiría viendo todo.
    """
    app, client = backend_client
    suffix = uuid4().hex[:8]
    headers = await _admin(app, client, suffix)

    areas = []
    for cual in ("A", "B"):
        area = await client.post(
            f"{API}/catalogos/areas",
            headers=headers,
            json={"codigo": f"FIL{cual}-{suffix}", "nombre": f"Área {cual} {suffix}"},
        )
        assert area.status_code == 201, area.text
        areas.append(area.json()["id"])

    catalogo_id = await poa_inicial_id(client, headers)
    anio = 2000 + (uuid4().int % 200)
    for _ in range(8):
        ejercicio = await client.post(
            f"{API}/poa/ejercicios",
            headers=headers,
            json={"anio": anio, "catalogo_id": catalogo_id},
        )
        if ejercicio.status_code == 201:
            break
        anio = 2000 + (uuid4().int % 200)
    else:
        raise AssertionError("No se encontró un año libre.")
    ejercicio_id = ejercicio.json()["id"]
    for estrategia, area_id in (("1.1", areas[0]), ("1.3", areas[1])):
        await _cedula_con_actividad(
            client,
            headers,
            ejercicio_id=ejercicio_id,
            anio=anio,
            estrategia=estrategia,
            area_id=area_id,
        )

    completo = await client.get(
        f"{API}/poa/reportes/cuatrimestral?ejercicio_id={ejercicio_id}", headers=headers
    )
    assert len({fila["area_ejecutora_id"] for fila in completo.json()["filas"]}) == 2

    filtrado = await client.get(
        f"{API}/poa/reportes/cuatrimestral?ejercicio_id={ejercicio_id}&area_id={areas[0]}",
        headers=headers,
    )

    assert filtrado.status_code == 200, filtrado.text
    assert {fila["area_ejecutora_id"] for fila in filtrado.json()["filas"]} == {areas[0]}


@pytest.mark.asyncio
async def test_rectoria_abre_el_poa_que_tiene_que_dictaminar(backend_client):
    """Aprobar a ciegas no es aprobar.

    Rectoría aprueba o devuelve el POA de toda la universidad, y la pantalla ya
    le ofrecía el ejercicio y sus cédulas; el backend respondía 403 a cada
    consulta, así que veía un error donde debía ver el POA. Se le abre la
    lectura completa —no tiene área, así que la regla del capturista la dejaba
    fuera de todas las cédulas— y ninguna escritura.
    """
    app, client = backend_client
    suffix = uuid4().hex[:8]
    headers = await _admin(app, client, suffix)
    rectoria = await _rectoria(app, client, suffix)

    area = await client.post(
        f"{API}/catalogos/areas",
        headers=headers,
        json={"codigo": f"DIC-{suffix}", "nombre": f"Área dictamen {suffix}"},
    )
    assert area.status_code == 201, area.text
    catalogo_id = await poa_inicial_id(client, headers)
    anio = 2000 + (uuid4().int % 200)
    for _ in range(8):
        ejercicio = await client.post(
            f"{API}/poa/ejercicios",
            headers=headers,
            json={"anio": anio, "catalogo_id": catalogo_id},
        )
        if ejercicio.status_code == 201:
            break
        anio = 2000 + (uuid4().int % 200)
    else:
        raise AssertionError("No se encontró un año libre.")
    ejercicio_id = ejercicio.json()["id"]
    cedula = await _cedula_con_actividad(
        client,
        headers,
        ejercicio_id=ejercicio_id,
        anio=anio,
        estrategia="1.1",
        area_id=area.json()["id"],
    )

    listado = await client.get(f"{API}/poa/ejercicios", headers=rectoria)
    assert listado.status_code == 200, listado.text
    assert any(item["id"] == ejercicio_id for item in listado.json())

    cedulas = await client.get(f"{API}/poa/cedulas?ejercicio_id={ejercicio_id}", headers=rectoria)
    assert cedulas.status_code == 200, cedulas.text
    assert [item["id"] for item in cedulas.json()] == [cedula["id"]]

    detalle = await client.get(f"{API}/poa/cedulas/{cedula['id']}", headers=rectoria)
    assert detalle.status_code == 200, detalle.text
    assert detalle.json()["estrategia_clave"] == "1.1"

    # Leer, no escribir: la formulación sigue siendo de Planeación.
    denegado = await client.patch(
        f"{API}/poa/cedulas/{cedula['id']}",
        headers=rectoria,
        json={"alcance_efecto_socioeconomico": "Lo cambio yo"},
    )
    assert denegado.status_code == 403, denegado.text
