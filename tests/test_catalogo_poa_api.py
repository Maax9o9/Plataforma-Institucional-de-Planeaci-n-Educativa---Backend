"""Los POA por HTTP: crearlos, listarlos, y que el catálogo pida de cuál."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest

from app.modules.identity_access.application.dto import RegisterUserCommand
from app.modules.identity_access.application.use_cases.create_user import CreateUser
from app.modules.identity_access.domain.value_objects import Role
from helpers import (
    IDS_QUE_NO_PUEDEN_SER_DE_UN_POA,
    POA_INEXISTENTE,
    crear_poa,
    poa_inicial_id,
)

API = "/api/v1"
CATALOGO = f"{API}/poa/catalogos"


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
@pytest.mark.parametrize("parte", LECTURAS)
async def test_leer_el_catalogo_exige_estar_autenticado(backend_client, parte):
    """«Leer el catálogo lo puede hacer cualquier autenticado» es una decisión
    -está razonada en `cedula_router.py:410-415`-, y hasta aquí nada la
    distinguía de dejarlo **público**: quitar las cuatro
    `_user=Depends(get_current_user)` de `list_objectives`, `list_strategies`,
    `list_indicators` y `list_activity_catalog` dejaba la suite entera en verde.
    Son exactamente los cuatro endpoints que durante este plan quedaron abiertos
    a cualquier autenticado por una afirmación falsa, así que lo que no está
    sujeto es el «autenticado».

    La misma petición se hace dos veces, con sesión y sin ella: el 200 de la
    primera es lo que demuestra que el 401 de la segunda mide la sesión y no la
    ruta, el POA ni el parámetro. Los cuatro se recorren porque basta que a uno
    le falte la guarda para que el catálogo entero se lea sin cuenta, igual que
    `/poa/catalogos-poa` tiene la suya.
    """
    app, client = backend_client
    headers = await _planeacion(app, client, uuid4().hex[:8])
    poa = await poa_inicial_id(client, headers)

    con_sesion = await client.get(f"{CATALOGO}/{parte}?catalogo_id={poa}", headers=headers)
    sin_sesion = await client.get(f"{CATALOGO}/{parte}?catalogo_id={poa}")

    assert con_sesion.status_code == 200, con_sesion.text
    assert sin_sesion.status_code == 401, sin_sesion.text


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


@pytest.mark.asyncio
@pytest.mark.parametrize(("catalogo_id", "tipo"), IDS_QUE_NO_PUEDEN_SER_DE_UN_POA)
@pytest.mark.parametrize(("metodo", "ruta", "cuerpo"), LOS_DOCE)
async def test_un_id_que_no_puede_ser_de_un_poa_es_422_y_no_404_ni_500(
    backend_client, metodo, ruta, cuerpo, catalogo_id, tipo
):
    """Un id que no cabe en el entero de 32 bits de la base no es un POA que no
    existe sino un valor que PostgreSQL ni acepta como parámetro: sin límite en la
    consulta llega hasta ahí y contesta 500, justo donde el contrato es 404. El
    cero tampoco es un POA que no existe: los ids son seriales y empiezan en 1."""
    app, client = backend_client
    headers = await _planeacion(app, client, uuid4().hex[:8])

    respuesta = await client.request(
        metodo, f"{CATALOGO}/{ruta}?catalogo_id={catalogo_id}", headers=headers, json=cuerpo
    )

    assert respuesta.status_code == 422, respuesta.text
    assert [(d["field"], d["type"]) for d in respuesta.json()["details"]] == [("catalogo_id", tipo)]


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
    inicial = await poa_inicial_id(client, headers)
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


#: Escrita a mano y no importada del router: si saliera de `PLANNING_ROLES`, un
#: rol que se quitara de ahí saldría también de la prueba y nadie se enteraría.
PUEDEN_CREAR_UN_POA = {Role.PLANEACION, Role.PLANEACION_ADMIN, Role.ADMIN_SISTEMA}


@pytest.mark.asyncio
@pytest.mark.parametrize("rol", list(Role))
async def test_sólo_planeación_crea_un_poa(backend_client, rol):
    """Los tres roles de Planeación pueden —el administrador del sistema
    incluido, que es quien da de alta todo lo demás— y los otros cinco no. Se
    recorre `Role` completo: un rol que se agregue mañana empieza prohibido, y
    la prueba lo exige hasta que alguien decida lo contrario aquí."""
    app, client = backend_client
    suffix = uuid4().hex[:8]
    headers = await _cuenta(app, client, rol, suffix)
    nombre = f"POA de {rol.value} {suffix}"
    puede = rol in PUEDEN_CREAR_UN_POA

    respuesta = await client.post(
        f"{API}/poa/catalogos-poa",
        headers=headers,
        json={"nombre": nombre, "anio": 2027, "origen": None},
    )

    assert respuesta.status_code == (201 if puede else 403), respuesta.text
    # Y quien no puede no deja nada: un 403 que además guardara sería peor.
    listado = await client.get(f"{API}/poa/catalogos-poa", headers=headers)
    assert (nombre in [p["nombre"] for p in listado.json()]) is puede


@pytest.mark.asyncio
@pytest.mark.parametrize("rol", list(Role))
async def test_cualquier_usuario_autenticado_ve_la_lista_de_poa(backend_client, rol):
    """Es la portada de un catálogo que cualquier autenticado ya lee entero: un
    índice más estrecho que su contenido no se sostiene. El revisor necesita
    saber de qué POA son las cédulas que revisa; quien formula o reporta, en cuál
    trabaja; Rectoría, contra cuál se formuló lo que va a aprobar. Se recorre
    `Role` completo para que un rol que se agregue mañana quede cubierto."""
    app, client = backend_client
    headers = await _cuenta(app, client, rol, uuid4().hex[:8])

    listado = await client.get(f"{API}/poa/catalogos-poa", headers=headers)

    assert listado.status_code == 200, listado.text


@pytest.mark.asyncio
async def test_la_lista_de_poa_exige_estar_autenticado(backend_client):
    _, client = backend_client

    listado = await client.get(f"{API}/poa/catalogos-poa")

    assert listado.status_code == 401, listado.text


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


# --- Una clave que no sea de dígitos y puntos ------------------------------

#: Lo que cada listado del catálogo tiene que devolver, en orden, y el orden en
#: que se da de alta (el inverso del texto, para que ni la inserción ni el
#: `ORDER BY clave` de la consulta acierten por su cuenta).
#:
#: `IND-1` no es un ejemplo inventado: es la forma que
#: `tests/test_instalacion_nueva.py` siembra como «un catálogo mínimo como el
#: que una instalación viva ya tenía». Y es alcanzable desde la interfaz: los
#: seis endpoints de administración declaran
#: `clave: str = PathParam(min_length=1, max_length=20)`, y el frontend sólo
#: exige dígitos para el objetivo.
CLAVES_ORDENADAS = {
    "estrategias": ["1.2", "1.10", "ESTR-A"],
    "indicadores": ["1.1.2", "1.1.10", "IND-1"],
    "actividades": ["1.2.2", "1.2.10", "ACC-A"],
}

#: El cuerpo que pide el alta de cada uno de los tres.
CUERPOS_DEL_ALTA = {
    "estrategias": lambda clave: {
        "objetivo_numero": 1,
        "denominacion": f"La estrategia {clave}",
    },
    "indicadores": lambda clave: {
        "objetivo_numero": 1,
        "nombre": f"El indicador {clave}",
        "formula": "(a / b) * 100",
        "unidad_medida": "Porcentaje",
    },
    "actividades": lambda clave: {
        "estrategia_clave": "1.2",
        "descripcion": f"La acción {clave}",
    },
}


@pytest.mark.asyncio
async def test_una_clave_que_no_es_de_digitos_no_tira_el_listado_del_catalogo(backend_client):
    """El catálogo es administrable y la clave la elige quien captura, así que
    un tramo puede no ser un número. Con `int()` a secas en la clave de orden,
    una sola fila como `IND-1` dejaba el listado entero en **500**
    (`ValueError: invalid literal for int() with base 10`), y no hay vuelta: no
    hay borrado -«retirar no borra»- y retirar exige listar, que es justo lo que
    revienta. La pestaña del POA se queda inservible hasta que alguien entre a
    la base a mano.

    Lo que se exige aquí es que **ordenar degrade con elegancia**, no que la
    clave se restrinja: qué forma puede tener una clave es decisión de producto.
    La parte numérica donde la haya, el texto como desempate y detrás.

    Las tres listas que ordenan por clave van en la misma prueba -estrategias,
    indicadores y acciones; los objetivos ordenan por número- y se da de alta en
    orden inverso al del texto, así que las reglas equivocadas no aciertan por
    casualidad: «como texto» daría `1.1.10` antes de `1.1.2`, «sin ordenar»
    devolvería el orden de inserción o el del `ORDER BY clave`, «numérico a
    secas» sigue siendo el 500, y «el texto primero» pondría `IND-1` al frente.
    """
    app, client = backend_client
    headers = await _planeacion(app, client, uuid4().hex[:8])
    poa = (await crear_poa(client, headers, 2033))["id"]
    catalogo = {"catalogo_id": poa}

    objetivo = await client.post(
        f"{CATALOGO}/objetivos/1",
        headers=headers,
        params=catalogo,
        json={"clave": "OBJ-1", "denominacion": "El objetivo 1"},
    )
    assert objetivo.status_code == 201, objetivo.text
    # Las estrategias primero: la acción exige que la suya exista.
    for parte in ("estrategias", "indicadores", "actividades"):
        for clave in sorted(CLAVES_ORDENADAS[parte], reverse=True):
            alta = await client.post(
                f"{CATALOGO}/{parte}/{clave}",
                headers=headers,
                params=catalogo,
                json=CUERPOS_DEL_ALTA[parte](clave),
            )
            assert alta.status_code == 201, alta.text

    listados = {}
    for parte in CLAVES_ORDENADAS:
        listado = await client.get(f"{CATALOGO}/{parte}", headers=headers, params=catalogo)
        assert listado.status_code == 200, listado.text
        listados[parte] = [item["clave"] for item in listado.json()]

    assert listados == CLAVES_ORDENADAS
