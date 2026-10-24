from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date
from itertools import count
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.app_factory import create_app
from app.core.config import Settings
from app.modules.identity_access.application.dto import RegisterUserCommand
from app.modules.identity_access.application.use_cases.create_user import CreateUser
from app.modules.identity_access.domain.value_objects import Role
from app.modules.institutional_catalogs.infrastructure.models import (
    InstrumentModel,
    InstrumentVersionModel,
)
from app.modules.institutional_catalogs.infrastructure.strategic_tree_sql_repository import (
    SqlAlchemyStrategicTreeRepository,
)

PIDE = "/api/v1/pide"
NODO_INEXISTENTE = 10**9
ENTERO_MAS_GRANDE_QUE_LA_BASE = 2**31
ENTERO_MAS_CHICO_QUE_LA_BASE = -(2**31) - 1
ENTERO_MAS_GRANDE_QUE_CABE = 2**31 - 1
ENTERO_MAS_CHICO_QUE_CABE = -(2**31)

ROLES_QUE_ESCRIBEN = (Role.PLANEACION, Role.ADMIN_SISTEMA, Role.PLANEACION_ADMIN)
ROLES_QUE_SOLO_LEEN = tuple(rol for rol in Role if rol not in ROLES_QUE_ESCRIBEN)

CUERPO_DE_UN_EJE = {"tipo": "eje", "clave": "NUEVO", "denominacion": "Un eje nuevo", "orden": 9}

VERSIONES_EN_MEMORIA = count(41)


@dataclass
class Escenario:
    app: object
    client: object
    cabeceras: dict[str, str]
    fabrica: async_sessionmaker | None
    version: int


async def _cabeceras(app, client, rol: Role) -> dict[str, str]:
    correo = f"arbol-pide-{rol.value}-{uuid4().hex[:8]}@example.com"
    await CreateUser(
        app.state.user_repository, app.state.password_hasher, app.state.event_bus
    ).execute(
        RegisterUserCommand(
            email=correo,
            full_name=f"Arbol PIDE {rol.value}",
            password="password-seguro",
            roles={rol},
            area_id=None,
        )
    )
    login = await client.post(
        "/api/v1/auth/login", json={"correo": correo, "contrasena": "password-seguro"}
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _version(fabrica: async_sessionmaker | None) -> int:
    if fabrica is None:
        return next(VERSIONES_EN_MEMORIA)
    async with fabrica() as sesion:
        instrumento = InstrumentModel(nombre=f"Instrumento de prueba {uuid4().hex[:8]}")
        sesion.add(instrumento)
        await sesion.flush()
        version = InstrumentVersionModel(
            instrumento_id=instrumento.id, etiqueta="V1", vigente_desde=date(2025, 1, 1)
        )
        sesion.add(version)
        await sesion.flush()
        version_id = version.id
        await sesion.commit()
    return version_id


@pytest.fixture
async def escenario(backend_client):
    app, client = backend_client
    cabeceras = await _cabeceras(app, client, Role.PLANEACION)
    if app.state.db_engine is None:
        yield Escenario(
            app=app,
            client=client,
            cabeceras=cabeceras,
            fabrica=None,
            version=await _version(None),
        )
        return
    async with app.state.db_engine.connect() as conexion:
        transaccion = await conexion.begin()
        fabrica = async_sessionmaker(
            bind=conexion, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        app.state.strategic_tree_repository = SqlAlchemyStrategicTreeRepository(fabrica)
        try:
            yield Escenario(
                app=app,
                client=client,
                cabeceras=cabeceras,
                fabrica=fabrica,
                version=await _version(fabrica),
            )
        finally:
            await transaccion.rollback()


async def _crear(
    escenario: Escenario,
    clave: str,
    tipo: str = "eje",
    *,
    padre: dict | None = None,
    orden: int = 1,
    **campos,
) -> dict:
    cuerpo = {
        "tipo": tipo,
        "clave": clave,
        "denominacion": f"Denominación de {clave}",
        "orden": orden,
        "padre_id": padre["id"] if padre else None,
        **campos,
    }
    respuesta = await escenario.client.post(
        f"{PIDE}/versiones/{escenario.version}/nodos",
        headers=escenario.cabeceras,
        json=cuerpo,
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


async def _listar(escenario: Escenario, version: int | None = None, **parametros) -> list[dict]:
    respuesta = await escenario.client.get(
        f"{PIDE}/versiones/{version or escenario.version}/nodos",
        headers=escenario.cabeceras,
        params=parametros,
    )
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


async def _retirar(escenario: Escenario, nodo: dict):
    return await escenario.client.post(
        f"{PIDE}/nodos/{nodo['id']}/desactivar", headers=escenario.cabeceras
    )


async def _corregir(escenario: Escenario, nodo: dict, cuerpo: dict):
    return await escenario.client.patch(
        f"{PIDE}/nodos/{nodo['id']}", headers=escenario.cabeceras, json=cuerpo
    )


def _peticion(nombre: str, version: int, nodo: int) -> tuple[str, str, dict | None]:
    return {
        "listar": ("GET", f"{PIDE}/versiones/{version}/nodos", None),
        "crear": ("POST", f"{PIDE}/versiones/{version}/nodos", CUERPO_DE_UN_EJE),
        "corregir": ("PATCH", f"{PIDE}/nodos/{nodo}", {"denominacion": "Corregida"}),
        "retirar": ("POST", f"{PIDE}/nodos/{nodo}/desactivar", None),
    }[nombre]


@pytest.mark.parametrize("peticion", ["listar", "crear", "corregir", "retirar"])
async def test_sin_sesion_el_arbol_contesta_401(escenario, peticion):
    eje = await _crear(escenario, "E1")
    metodo, url, cuerpo = _peticion(peticion, escenario.version, eje["id"])

    respuesta = await escenario.client.request(metodo, url, json=cuerpo)

    assert respuesta.status_code == 401, respuesta.text


@pytest.mark.parametrize("escritura", ["crear", "corregir", "retirar"])
@pytest.mark.parametrize("rol", ROLES_QUE_SOLO_LEEN, ids=lambda rol: rol.value)
async def test_quien_solo_lee_no_puede_escribir_el_arbol(escenario, rol, escritura):
    eje = await _crear(escenario, "E1")
    cabeceras = await _cabeceras(escenario.app, escenario.client, rol)
    metodo, url, cuerpo = _peticion(escritura, escenario.version, eje["id"])
    lectura = await escenario.client.get(
        f"{PIDE}/versiones/{escenario.version}/nodos", headers=cabeceras
    )
    assert lectura.status_code == 200, lectura.text

    respuesta = await escenario.client.request(metodo, url, headers=cabeceras, json=cuerpo)

    assert respuesta.status_code == 403, respuesta.text
    assert respuesta.json()["code"] == "FORBIDDEN"
    assert await _listar(escenario) == [eje]


@pytest.mark.parametrize("rol", list(Role), ids=lambda rol: rol.value)
async def test_cualquier_rol_autenticado_lee_el_arbol(escenario, rol):
    eje = await _crear(escenario, "E1")
    cabeceras = await _cabeceras(escenario.app, escenario.client, rol)

    respuesta = await escenario.client.get(
        f"{PIDE}/versiones/{escenario.version}/nodos", headers=cabeceras
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == [eje]


@pytest.mark.parametrize("rol", ROLES_QUE_ESCRIBEN, ids=lambda rol: rol.value)
async def test_los_roles_de_escritura_crean_corrigen_y_retiran(escenario, rol):
    como_el_rol = replace(
        escenario, cabeceras=await _cabeceras(escenario.app, escenario.client, rol)
    )

    creado = await _crear(como_el_rol, "E1")
    corregido = await _corregir(como_el_rol, creado, {"denominacion": "Corregida"})
    retirado = await _retirar(como_el_rol, creado)

    assert corregido.status_code == 200, corregido.text
    assert corregido.json()["denominacion"] == "Corregida"
    assert retirado.status_code == 200, retirado.text
    assert retirado.json()["activo"] is False


async def test_el_arbol_llega_en_orden_de_recorrido(escenario):
    e2 = await _crear(escenario, "E2", orden=2)
    await _crear(escenario, "E2.O1", "objetivo_general", padre=e2, orden=1)
    await _crear(escenario, "E10", orden=3)
    e1 = await _crear(escenario, "E1", orden=1)
    await _crear(escenario, "E1.O2", "objetivo_general", padre=e1, orden=2)
    e1_o1 = await _crear(escenario, "E1.O1", "objetivo_general", padre=e1, orden=1)
    await _crear(escenario, "E1.O1.1", "objetivo_especifico", padre=e1_o1, orden=1)

    nodos = await _listar(escenario)

    assert [(nodo["clave"], nodo["padre_id"]) for nodo in nodos] == [
        ("E1", None),
        ("E1.O1", e1["id"]),
        ("E1.O1.1", e1_o1["id"]),
        ("E1.O2", e1["id"]),
        ("E2", None),
        ("E2.O1", e2["id"]),
        ("E10", None),
    ]


async def test_lo_retirado_solo_llega_si_se_pide(escenario):
    eje = await _crear(escenario, "E1")
    hoja = await _crear(escenario, "E1.O1", "objetivo_general", padre=eje)
    assert (await _retirar(escenario, hoja)).status_code == 200

    por_omision = await _listar(escenario)
    pidiendolo = await _listar(escenario, incluir_inactivos=True)
    sin_pedirlo = await _listar(escenario, incluir_inactivos=False)

    assert [nodo["clave"] for nodo in por_omision] == ["E1"]
    assert [(nodo["clave"], nodo["activo"]) for nodo in pidiendolo] == [
        ("E1", True),
        ("E1.O1", False),
    ]
    assert por_omision == sin_pedirlo


async def test_un_nodo_creado_queda_en_su_version_con_cada_campo(escenario):
    otra_version = await _version(escenario.fabrica)
    eje = await _crear(escenario, "E1")

    creado = await _crear(
        escenario,
        "L-9",
        "linea_estrategica",
        padre=eje,
        orden=7,
        denominacion="Fortalecer la vinculación",
        formula_indicador="(a / b) * 100",
    )

    assert isinstance(creado["id"], int)
    assert {campo: valor for campo, valor in creado.items() if campo != "id"} == {
        "version_id": escenario.version,
        "padre_id": eje["id"],
        "tipo": "linea_estrategica",
        "clave": "L-9",
        "denominacion": "Fortalecer la vinculación",
        "orden": 7,
        "activo": True,
        "formula_indicador": "(a / b) * 100",
    }
    assert [nodo["clave"] for nodo in await _listar(escenario)] == ["E1", "L-9"]
    assert await _listar(escenario, otra_version) == []


async def test_corregir_un_campo_no_toca_los_demas(escenario):
    eje = await _crear(escenario, "E1")
    nodo = await _crear(
        escenario,
        "L-9",
        "linea_estrategica",
        padre=eje,
        orden=7,
        formula_indicador="(a / b) * 100",
    )

    corregido = await _corregir(escenario, nodo, {"denominacion": "Otra denominación"})

    esperado = {**nodo, "denominacion": "Otra denominación"}
    assert corregido.status_code == 200, corregido.text
    assert corregido.json() == esperado
    assert [n for n in await _listar(escenario) if n["id"] == nodo["id"]] == [esperado]


async def test_corregir_varios_campos_deja_cada_uno_en_su_sitio(escenario):
    eje = await _crear(escenario, "E1", orden=1)
    otro_eje = await _crear(escenario, "E2", orden=2)
    nodo = await _crear(escenario, "O1", "objetivo_general", padre=eje, orden=4)

    corregido = await _corregir(
        escenario,
        nodo,
        {
            "tipo": "linea_estrategica",
            "clave": "L-3",
            "denominacion": "Otra denominación",
            "orden": 8,
            "padre_id": otro_eje["id"],
            "formula_indicador": "a + b",
        },
    )

    esperado = {
        **nodo,
        "tipo": "linea_estrategica",
        "clave": "L-3",
        "denominacion": "Otra denominación",
        "orden": 8,
        "padre_id": otro_eje["id"],
        "formula_indicador": "a + b",
    }
    assert corregido.status_code == 200, corregido.text
    assert corregido.json() == esperado
    assert [n for n in await _listar(escenario) if n["id"] == nodo["id"]] == [esperado]


async def test_un_null_explicito_vacia_el_padre_y_la_formula(escenario):
    eje = await _crear(escenario, "E1")
    accion = await _crear(escenario, "A1", "accion", padre=eje, formula_indicador="(a / b) * 100")

    corregido = await _corregir(escenario, accion, {"padre_id": None, "formula_indicador": None})

    assert corregido.status_code == 200, corregido.text
    assert corregido.json() == {**accion, "padre_id": None, "formula_indicador": None}
    assert [(n["clave"], n["padre_id"]) for n in await _listar(escenario)] == [
        ("E1", None),
        ("A1", None),
    ]


async def test_retirar_con_activos_colgando_se_niega_y_dice_cuantos(escenario):
    eje = await _crear(escenario, "EJE")
    objetivo_a = await _crear(escenario, "A", "objetivo_general", padre=eje, orden=1)
    await _crear(escenario, "B", "objetivo_general", padre=eje, orden=2)
    retirado = await _crear(escenario, "C", "objetivo_general", padre=eje, orden=3)
    await _crear(escenario, "AA", "objetivo_especifico", padre=objetivo_a)
    assert (await _retirar(escenario, retirado)).status_code == 200

    respuesta = await _retirar(escenario, eje)

    assert (respuesta.status_code, respuesta.json()["code"]) == CONFLICTO, respuesta.text
    assert re.findall(r"\d+", respuesta.json()["message"]) == ["2"]
    assert [
        (n["clave"], n["activo"]) for n in await _listar(escenario, incluir_inactivos=True)
    ] == [
        ("EJE", True),
        ("A", True),
        ("AA", True),
        ("B", True),
        ("C", False),
    ]


async def test_retirar_un_nodo_cuyos_hijos_ya_estan_retirados_si_se_puede_y_se_repite(escenario):
    eje = await _crear(escenario, "E1")
    hijo = await _crear(escenario, "E1.O1", "objetivo_general", padre=eje)
    assert (await _retirar(escenario, hijo)).status_code == 200

    primera = await _retirar(escenario, eje)
    segunda = await _retirar(escenario, eje)

    assert primera.status_code == 200, primera.text
    assert primera.json() == {**eje, "activo": False}
    assert segunda.status_code == 200, segunda.text
    assert segunda.json() == {**eje, "activo": False}
    assert [
        (n["clave"], n["activo"]) for n in await _listar(escenario, incluir_inactivos=True)
    ] == [
        ("E1", False),
        ("E1.O1", False),
    ]


async def test_un_nodo_retirado_vuelve_con_patch_activo_pero_no_bajo_un_padre_retirado(escenario):
    eje = await _crear(escenario, "E1")
    hijo = await _crear(escenario, "E1.O1", "objetivo_general", padre=eje)
    assert (await _retirar(escenario, hijo)).status_code == 200
    assert (await _retirar(escenario, eje)).status_code == 200

    bajo_un_padre_retirado = await _corregir(escenario, hijo, {"activo": True})
    el_padre = await _corregir(escenario, eje, {"activo": True})
    el_hijo = await _corregir(escenario, hijo, {"activo": True})

    assert bajo_un_padre_retirado.status_code == 422, bajo_un_padre_retirado.text
    assert el_padre.status_code == 200, el_padre.text
    assert el_padre.json()["activo"] is True
    assert el_hijo.status_code == 200, el_hijo.text
    assert [n["clave"] for n in await _listar(escenario)] == ["E1", "E1.O1"]


@pytest.mark.parametrize("escritura", ["corregir", "retirar"])
async def test_un_nodo_que_no_existe_contesta_404(escenario, escritura):
    metodo, url, cuerpo = _peticion(escritura, escenario.version, NODO_INEXISTENTE)

    respuesta = await escenario.client.request(
        metodo, url, headers=escenario.cabeceras, json=cuerpo
    )

    assert respuesta.status_code == 404, respuesta.text
    assert respuesta.json()["code"] == "RESOURCE_NOT_FOUND"


CONFLICTO = (409, "CONFLICT")
NO_CUMPLE_LAS_REGLAS = (422, "BUSINESS_VALIDATION_ERROR")

ERRORES_DEL_DOMINIO = {
    "clave_repetida_entre_las_raices": (
        lambda e, n: (
            "POST",
            f"{PIDE}/versiones/{e.version}/nodos",
            {**CUERPO_DE_UN_EJE, "clave": "E1"},
        ),
        CONFLICTO,
    ),
    "eje_colgado_de_un_eje": (
        lambda e, n: (
            "POST",
            f"{PIDE}/versiones/{e.version}/nodos",
            {**CUERPO_DE_UN_EJE, "padre_id": n["eje"]["id"]},
        ),
        NO_CUMPLE_LAS_REGLAS,
    ),
    "padre_que_no_existe": (
        lambda e, n: (
            "POST",
            f"{PIDE}/versiones/{e.version}/nodos",
            {**CUERPO_DE_UN_EJE, "padre_id": NODO_INEXISTENTE},
        ),
        NO_CUMPLE_LAS_REGLAS,
    ),
    "nivel_que_el_pide_no_tiene": (
        lambda e, n: (
            "POST",
            f"{PIDE}/versiones/{e.version}/nodos",
            {**CUERPO_DE_UN_EJE, "tipo": "capitulo"},
        ),
        NO_CUMPLE_LAS_REGLAS,
    ),
    "clave_en_blanco": (
        lambda e, n: (
            "POST",
            f"{PIDE}/versiones/{e.version}/nodos",
            {**CUERPO_DE_UN_EJE, "clave": "   "},
        ),
        NO_CUMPLE_LAS_REGLAS,
    ),
    "clave_de_un_hermano": (
        lambda e, n: ("PATCH", f"{PIDE}/nodos/{n['eje']['id']}", {"clave": "E2"}),
        CONFLICTO,
    ),
    "nivel_que_no_queda_mas_abajo_que_su_padre": (
        lambda e, n: ("PATCH", f"{PIDE}/nodos/{n['hijo']['id']}", {"tipo": "eje"}),
        NO_CUMPLE_LAS_REGLAS,
    ),
}


@pytest.mark.parametrize("caso", list(ERRORES_DEL_DOMINIO))
async def test_los_errores_del_dominio_llegan_con_su_codigo_y_no_dejan_nada_escrito(
    escenario, caso
):
    eje = await _crear(escenario, "E1")
    await _crear(escenario, "E2", orden=2)
    hijo = await _crear(escenario, "E1.O1", "objetivo_general", padre=eje)
    antes = await _listar(escenario, incluir_inactivos=True)
    peticion, (estado, codigo) = ERRORES_DEL_DOMINIO[caso]
    metodo, url, cuerpo = peticion(escenario, {"eje": eje, "hijo": hijo})

    respuesta = await escenario.client.request(
        metodo, url, headers=escenario.cabeceras, json=cuerpo
    )

    assert respuesta.status_code == estado, respuesta.text
    assert respuesta.json()["code"] == codigo
    assert await _listar(escenario, incluir_inactivos=True) == antes


@pytest.mark.parametrize(
    "valor",
    [ENTERO_MAS_GRANDE_QUE_LA_BASE, ENTERO_MAS_CHICO_QUE_LA_BASE, 0],
    ids=["mayor_que_el_entero_de_la_base", "menor_que_el_entero_de_la_base", "cero"],
)
@pytest.mark.parametrize("peticion", ["listar", "crear", "corregir", "retirar"])
async def test_un_id_que_la_base_no_acepta_se_rechaza_antes_de_llegar_a_ella(
    escenario, peticion, valor
):
    metodo, url, cuerpo = _peticion(peticion, valor, valor)

    respuesta = await escenario.client.request(
        metodo, url, headers=escenario.cabeceras, json=cuerpo
    )

    assert respuesta.status_code == 422, respuesta.text
    assert respuesta.json()["code"] == "REQUEST_VALIDATION_ERROR"


@pytest.mark.parametrize(
    ("peticion", "id_", "estado"),
    [
        ("listar", ENTERO_MAS_GRANDE_QUE_CABE, 200),
        ("listar", 1, 200),
        ("corregir", ENTERO_MAS_GRANDE_QUE_CABE, 404),
        ("retirar", ENTERO_MAS_GRANDE_QUE_CABE, 404),
    ],
    ids=["version_mayor", "version_uno", "nodo_mayor_corregir", "nodo_mayor_retirar"],
)
async def test_los_extremos_de_lo_que_la_base_acepta_son_ids_validos(
    escenario, peticion, id_, estado
):
    metodo, url, cuerpo = _peticion(peticion, id_, id_)

    respuesta = await escenario.client.request(
        metodo, url, headers=escenario.cabeceras, json=cuerpo
    )

    assert respuesta.status_code == estado, respuesta.text


async def test_el_padre_mas_grande_que_cabe_es_un_id_valido_que_no_existe(escenario):
    respuesta = await escenario.client.post(
        f"{PIDE}/versiones/{escenario.version}/nodos",
        headers=escenario.cabeceras,
        json={**CUERPO_DE_UN_EJE, "padre_id": ENTERO_MAS_GRANDE_QUE_CABE},
    )

    assert respuesta.status_code == 422, respuesta.text
    assert respuesta.json()["code"] == "BUSINESS_VALIDATION_ERROR"


@pytest.mark.parametrize("orden", [ENTERO_MAS_GRANDE_QUE_CABE, ENTERO_MAS_CHICO_QUE_CABE])
async def test_el_orden_acepta_los_extremos_del_entero_de_la_base(escenario, orden):
    nodo = await _crear(escenario, "E1", orden=orden)

    assert nodo["orden"] == orden
    assert await _listar(escenario) == [nodo]


@pytest.mark.parametrize("escritura", ["crear", "corregir"])
@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("padre_id", ENTERO_MAS_GRANDE_QUE_LA_BASE),
        ("padre_id", 0),
        ("orden", ENTERO_MAS_GRANDE_QUE_LA_BASE),
        ("orden", ENTERO_MAS_CHICO_QUE_LA_BASE),
    ],
)
async def test_un_entero_del_cuerpo_que_la_base_no_acepta_se_rechaza_antes_de_llegar_a_ella(
    escenario, escritura, campo, valor
):
    eje = await _crear(escenario, "E1")
    _, url, cuerpo = _peticion(escritura, escenario.version, eje["id"])
    metodo = "POST" if escritura == "crear" else "PATCH"

    respuesta = await escenario.client.request(
        metodo, url, headers=escenario.cabeceras, json={**cuerpo, campo: valor}
    )

    assert respuesta.status_code == 422, respuesta.text
    assert respuesta.json()["code"] == "REQUEST_VALIDATION_ERROR"
    assert await _listar(escenario) == [eje]


@pytest.mark.parametrize(
    ("escritura", "ajeno"),
    [
        ("crear", {"activo": False}),
        ("crear", {"version_id": 7}),
        ("corregir", {"version_id": 7}),
        ("corregir", {"id": 7}),
    ],
    ids=["crear_activo", "crear_version", "corregir_version", "corregir_id"],
)
async def test_un_campo_que_el_nodo_no_tiene_se_rechaza_y_no_se_ignora(escenario, escritura, ajeno):
    eje = await _crear(escenario, "E1")
    metodo, url, cuerpo = _peticion(escritura, escenario.version, eje["id"])

    respuesta = await escenario.client.request(
        metodo, url, headers=escenario.cabeceras, json={**cuerpo, **ajeno}
    )

    assert respuesta.status_code == 422, respuesta.text
    assert respuesta.json()["code"] == "REQUEST_VALIDATION_ERROR"
    assert await _listar(escenario, incluir_inactivos=True) == [eje]


@pytest.mark.parametrize("campo", ["tipo", "clave", "denominacion", "orden", "activo"])
async def test_un_null_explicito_se_rechaza_donde_el_nodo_no_admite_nulo(escenario, campo):
    eje = await _crear(escenario, "E1")

    respuesta = await _corregir(escenario, eje, {campo: None})

    assert respuesta.status_code == 422, respuesta.text
    assert respuesta.json()["code"] == "REQUEST_VALIDATION_ERROR"
    assert await _listar(escenario, incluir_inactivos=True) == [eje]


def test_el_arbol_del_pide_se_publica_aunque_el_modulo_de_indicadores_duerma():
    rutas = create_app(
        Settings(
            environment="testing",
            secret_key="test-secret-key-with-more-than-32-characters",
            database_url=None,
            email_provider="console",
            indicators_module_enabled=False,
        )
    ).openapi()["paths"]

    assert {
        ruta: set(metodos) for ruta, metodos in rutas.items() if ruta.startswith(f"{PIDE}/")
    } == {
        f"{PIDE}/versiones/{{version_id}}/nodos": {"get", "post"},
        f"{PIDE}/nodos/{{nodo_id}}": {"patch"},
        f"{PIDE}/nodos/{{nodo_id}}/desactivar": {"post"},
    }
