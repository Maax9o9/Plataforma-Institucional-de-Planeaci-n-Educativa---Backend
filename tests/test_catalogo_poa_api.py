"""Los POA por HTTP: crearlos, listarlos, y que el catálogo pida de cuál."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest

from app.modules.identity_access.application.dto import RegisterUserCommand
from app.modules.identity_access.application.use_cases.create_user import CreateUser
from app.modules.identity_access.domain.value_objects import Role

API = "/api/v1"
CATALOGO = f"{API}/poa/catalogos"
#: Un id que ningún POA tiene. La base de pruebas es persistente y el id es
#: serial: con uno chico, tarde o temprano habría un POA que lo use.
POA_INEXISTENTE = 999999


async def _cuenta(app, client, rol: Role, suffix: str) -> dict[str, str]:
    email = f"poa-api-{rol.value}-{suffix}@example.com"
    await CreateUser(
        app.state.user_repository, app.state.password_hasher, app.state.event_bus
    ).execute(
        RegisterUserCommand(
            email=email,
            full_name=f"POA API {rol.value}",
            password="password-seguro",
            roles={rol},
            area_id=None,
        )
    )
    login = await client.post(
        f"{API}/auth/login", json={"correo": email, "contrasena": "password-seguro"}
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _planeacion(app, client, suffix: str) -> dict[str, str]:
    return await _cuenta(app, client, Role.PLANEACION, suffix)


@pytest.mark.asyncio
async def test_crear_y_listar_un_poa(backend_client):
    app, client = backend_client
    headers = await _planeacion(app, client, uuid4().hex[:8])
    nombre = f"POA de prueba {uuid4().hex[:6]}"

    creado = await client.post(
        f"{API}/poa/catalogos-poa",
        headers=headers,
        json={"nombre": nombre, "anio": 2027, "origen": "capturado a mano"},
    )

    assert creado.status_code == 201, creado.text
    assert creado.json()["nombre"] == nombre
    assert creado.json()["origen"] == "capturado a mano"
    assert creado.json()["anio"] == 2027
    assert set(creado.json()) == {
        "id",
        "nombre",
        "anio",
        "origen",
        "creado_en",
        "actualizado_en",
    }

    listado = await client.get(f"{API}/poa/catalogos-poa", headers=headers)
    assert listado.status_code == 200, listado.text
    assert any(p["nombre"] == nombre for p in listado.json())


@pytest.mark.asyncio
async def test_un_poa_nuevo_nace_vacío(backend_client):
    """El camino lento: se crea vacío y se llena con el CRUD. El selector de
    estrategias tiene que devolver una lista vacía, no reventar."""
    app, client = backend_client
    headers = await _planeacion(app, client, uuid4().hex[:8])
    creado = await client.post(
        f"{API}/poa/catalogos-poa",
        headers=headers,
        json={"nombre": f"POA vacío {uuid4().hex[:6]}", "anio": 2028, "origen": None},
    )
    assert creado.status_code == 201, creado.text
    catalogo_id = creado.json()["id"]

    estrategias = await client.get(
        f"{API}/poa/catalogos/estrategias?catalogo_id={catalogo_id}", headers=headers
    )

    assert estrategias.status_code == 200, estrategias.text
    assert estrategias.json() == []


# --- Los doce endpoints del catálogo ---------------------------------------
#
# Cuatro lecturas y ocho escrituras (un alta y una corrección por cada tipo).
# Las claves de las altas son las que el POA inicial ya tiene —el objetivo 1,
# la estrategia 1.1—: así, cuando una alta cae en el POA equivocado, choca.

LECTURAS = ("objetivos", "estrategias", "indicadores", "actividades")

ALTAS = {
    "objetivos/1": {"clave": "OBJ-1", "denominacion": "Objetivo del otro POA"},
    "estrategias/1.1": {"objetivo_numero": 1, "denominacion": "Estrategia del otro POA"},
    "indicadores/1.1.14": {
        "objetivo_numero": 1,
        "nombre": "Indicador del otro POA",
        "formula": "(a / b) * 100",
        "unidad_medida": "Porcentaje",
    },
    "actividades/1.1.2": {"estrategia_clave": "1.1", "descripcion": "Acción del otro POA"},
}

CORRECCIONES = {
    "objetivos/1": {"clave": "OBJ-1", "denominacion": "Texto corregido", "activo": False},
    "estrategias/1.1": {
        "objetivo_numero": 1,
        "denominacion": "Texto corregido",
        "activo": False,
    },
    "indicadores/1.1.14": {
        "objetivo_numero": 1,
        "nombre": "Texto corregido",
        "formula": "(a / b) * 100",
        "unidad_medida": "Porcentaje",
        "activo": False,
    },
    "actividades/1.1.2": {
        "estrategia_clave": "1.1",
        "descripcion": "Texto corregido",
        "activo": False,
    },
}

LOS_DOCE = [
    *(pytest.param("GET", parte, None, id=f"GET-{parte}") for parte in LECTURAS),
    *(pytest.param("POST", ruta, cuerpo, id=f"POST-{ruta}") for ruta, cuerpo in ALTAS.items()),
    *(
        pytest.param("PATCH", ruta, cuerpo, id=f"PATCH-{ruta}")
        for ruta, cuerpo in CORRECCIONES.items()
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("metodo", "ruta", "cuerpo"), LOS_DOCE)
async def test_el_catalogo_exige_decir_de_qué_poa(backend_client, metodo, ruta, cuerpo):
    """Sin el POA la consulta no tiene respuesta correcta posible: devolver el
    de cualquier año sería peor que fallar. Lo exige Pydantic, no una
    comprobación a mano, y el cuerpo del 422 dice qué parámetro falta. Son
    doce porque basta que uno solo tenga valor por omisión para que una
    pantalla olvidadiza edite el POA de otro año sin que nadie se entere."""
    app, client = backend_client
    headers = await _planeacion(app, client, uuid4().hex[:8])

    sin_poa = await client.request(metodo, f"{CATALOGO}/{ruta}", headers=headers, json=cuerpo)

    assert sin_poa.status_code == 422, sin_poa.text
    assert [(d["field"], d["type"]) for d in sin_poa.json()["details"]] == [
        ("catalogo_id", "missing")
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(("metodo", "ruta", "cuerpo"), LOS_DOCE)
async def test_un_poa_que_no_existe_es_404_en_los_doce(backend_client, metodo, ruta, cuerpo):
    """Una lista vacía se leería en pantalla como «este POA no tiene
    estrategias» cuando la verdad es que el POA no existe. Y una escritura no
    puede dejar filas colgando de un POA que no está (en memoria las dejaría; en
    PostgreSQL reventaría con la llave foránea cruda)."""
    app, client = backend_client
    headers = await _planeacion(app, client, uuid4().hex[:8])

    respuesta = await client.request(
        metodo,
        f"{CATALOGO}/{ruta}?catalogo_id={POA_INEXISTENTE}",
        headers=headers,
        json=cuerpo,
    )

    assert respuesta.status_code == 404, respuesta.text
    # El mensaje dice qué es lo que no existe: el catálogo del POA, no el
    # elemento que se iba a editar.
    assert f"El POA {POA_INEXISTENTE} no existe." == respuesta.json()["message"]


async def _poa_inicial(client, headers) -> int:
    listado = await client.get(f"{API}/poa/catalogos-poa", headers=headers)
    assert listado.status_code == 200, listado.text
    return next(p["id"] for p in listado.json() if p["nombre"] == "POA 2026")


async def _fechas(client, headers) -> dict[int, datetime]:
    listado = await client.get(f"{API}/poa/catalogos-poa", headers=headers)
    assert listado.status_code == 200, listado.text
    return {p["id"]: datetime.fromisoformat(p["actualizado_en"]) for p in listado.json()}


async def _contenido(client, headers, catalogo_id: int) -> dict[str, list[dict]]:
    contenido = {}
    for parte in LECTURAS:
        respuesta = await client.get(
            f"{CATALOGO}/{parte}?catalogo_id={catalogo_id}&solo_activos=false", headers=headers
        )
        assert respuesta.status_code == 200, respuesta.text
        contenido[parte] = respuesta.json()
    return contenido


@pytest.mark.asyncio
async def test_cada_endpoint_trabaja_sobre_el_poa_que_se_le_pidió(backend_client):
    """Lo que Planeación pidió textualmente: que cambiar la información de un
    POA no cambie la del 2026. Las ocho escrituras y las cuatro lecturas van
    contra un POA nuevo con las mismas claves que el inicial; si alguna
    ignorara el `catalogo_id` y cayera en el inicial, el alta chocaría con una
    clave que ya existe, o el inicial amanecería editado."""
    app, client = backend_client
    headers = await _planeacion(app, client, uuid4().hex[:8])
    inicial = await _poa_inicial(client, headers)
    otro = await client.post(
        f"{API}/poa/catalogos-poa",
        headers=headers,
        json={"nombre": f"POA aparte {uuid4().hex[:6]}", "anio": 2029, "origen": None},
    )
    assert otro.status_code == 201, otro.text
    otro_id = otro.json()["id"]
    inicial_antes = await _contenido(client, headers, inicial)
    fechas_antes = await _fechas(client, headers)
    # Sin contenido en el inicial la prueba no demostraría nada.
    assert all(inicial_antes[parte] for parte in LECTURAS)
    assert await _contenido(client, headers, otro_id) == {parte: [] for parte in LECTURAS}

    for ruta, cuerpo in ALTAS.items():
        alta = await client.post(
            f"{CATALOGO}/{ruta}?catalogo_id={otro_id}", headers=headers, json=cuerpo
        )
        assert alta.status_code == 201, alta.text
    for ruta, cuerpo in CORRECCIONES.items():
        correccion = await client.patch(
            f"{CATALOGO}/{ruta}?catalogo_id={otro_id}", headers=headers, json=cuerpo
        )
        assert correccion.status_code == 200, correccion.text

    assert await _contenido(client, headers, otro_id) == {
        "objetivos": [
            {"clave": "OBJ-1", "numero": 1, "denominacion": "Texto corregido", "activo": False}
        ],
        "estrategias": [
            {
                "clave": "1.1",
                "objetivo_numero": 1,
                "denominacion": "Texto corregido",
                "activo": False,
            }
        ],
        "indicadores": [
            {
                "clave": "1.1.14",
                "objetivo_numero": 1,
                "nombre": "Texto corregido",
                "formula": "(a / b) * 100",
                "unidad_medida": "Porcentaje",
                "activo": False,
            }
        ],
        "actividades": [
            {
                "clave": "1.1.2",
                "estrategia_clave": "1.1",
                "descripcion": "Texto corregido",
                "activo": False,
            }
        ],
    }
    assert await _contenido(client, headers, inicial) == inicial_antes
    fechas_despues = await _fechas(client, headers)
    assert fechas_despues[inicial] == fechas_antes[inicial]
    assert fechas_despues[otro_id] > fechas_antes[otro_id]


# --- Quién puede qué --------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("rol", [Role.CAPTURISTA_POA, Role.RECTORIA, Role.CONSULTA])
async def test_sólo_planeación_crea_un_poa(backend_client, rol):
    app, client = backend_client
    suffix = uuid4().hex[:8]
    intruso = await _cuenta(app, client, rol, suffix)
    planeacion = await _planeacion(app, client, suffix)
    nombre = f"POA del intruso {suffix}"

    denegado = await client.post(
        f"{API}/poa/catalogos-poa",
        headers=intruso,
        json={"nombre": nombre, "anio": 2027, "origen": None},
    )

    assert denegado.status_code == 403, denegado.text
    listado = await client.get(f"{API}/poa/catalogos-poa", headers=planeacion)
    assert nombre not in [p["nombre"] for p in listado.json()]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("rol", "esperado"),
    [
        (Role.PLANEACION, 200),
        (Role.CAPTURISTA_POA, 200),
        # Rectoría ve contra qué POA se formuló lo que va a aprobar: sin esto
        # el menú le ofrece pantallas que contestan 403.
        (Role.RECTORIA, 200),
        (Role.CONSULTA, 403),
    ],
)
async def test_los_roles_que_leen_la_cédula_ven_la_lista_de_poa(backend_client, rol, esperado):
    app, client = backend_client
    headers = await _cuenta(app, client, rol, uuid4().hex[:8])

    listado = await client.get(f"{API}/poa/catalogos-poa", headers=headers)

    assert listado.status_code == esperado, listado.text


# --- Lo que el alta rechaza -------------------------------------------------


@pytest.mark.asyncio
async def test_dos_poa_no_pueden_llamarse_igual(backend_client):
    app, client = backend_client
    headers = await _planeacion(app, client, uuid4().hex[:8])
    nombre = f"POA repetido {uuid4().hex[:6]}"
    cuerpo = {"nombre": nombre, "anio": 2027, "origen": None}
    primero = await client.post(f"{API}/poa/catalogos-poa", headers=headers, json=cuerpo)
    assert primero.status_code == 201, primero.text

    repetido = await client.post(f"{API}/poa/catalogos-poa", headers=headers, json=cuerpo)

    assert repetido.status_code == 409, repetido.text
    assert nombre in repetido.json()["message"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cuerpo",
    [
        {"nombre": "", "anio": 2027},
        {"nombre": "   ", "anio": 2027},
        # La columna es VARCHAR(120): sin tope en el esquema, PostgreSQL
        # contestaría 500 y la memoria aceptaría lo que la base no admite.
        {"nombre": "x" * 121, "anio": 2027},
        {"nombre": "POA con año de antes", "anio": 1999},
        {"nombre": "POA con año de después", "anio": 2201},
    ],
    ids=["vacío", "sólo espacios", "121 letras", "año 1999", "año 2201"],
)
async def test_el_alta_de_un_poa_rechaza_lo_que_la_base_no_admite(backend_client, cuerpo):
    app, client = backend_client
    headers = await _planeacion(app, client, uuid4().hex[:8])

    respuesta = await client.post(f"{API}/poa/catalogos-poa", headers=headers, json=cuerpo)

    assert respuesta.status_code == 422, respuesta.text
