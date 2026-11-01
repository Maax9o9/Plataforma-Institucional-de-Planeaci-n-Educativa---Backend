from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from itertools import count
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.modules.identity_access.domain.value_objects import Role
from app.modules.institutional_catalogs.domain.strategic_tree_entities import (
    MAYOR_ENTERO_DE_LA_BASE,
)
from app.modules.institutional_catalogs.infrastructure.models import (
    InstrumentModel,
    InstrumentVersionModel,
)
from app.modules.institutional_catalogs.infrastructure.strategic_tree_sql_repository import (
    SqlAlchemyStrategicTreeRepository,
)
from app.modules.poa_institucional.api.schemas import EL_NULO_NO_ES_LEGAL_AQUI
from app.modules.poa_institucional.domain.entities import (
    EL_AREA_NO_EXISTE,
    EL_EJERCICIO_POA_NO_EXISTE,
    EL_POA_DEL_AREA_NO_SE_PUEDE_ENVIAR,
)
from app.modules.poa_institucional.infrastructure.sql_repository import (
    SqlAlchemyPoaAreaRepository,
)
from app.shared.domain.exceptions import ConflictError
from helpers import API, anio_libre, crear_ejercicio, crear_poa

POA_INST = f"{API}/poa-institucional"

VERSIONES_EN_MEMORIA = count(9001)

DOCE_METAS_QUE_SUMAN_24 = (
    Decimal(1),
    Decimal(3),
    Decimal(0),
    Decimal(2),
    Decimal(5),
    Decimal(1),
    Decimal(4),
    Decimal(0),
    Decimal(2),
    Decimal(1),
    Decimal(3),
    Decimal(2),
)

ENDPOINTS = ("consultar", "abrir", "registrar", "corregir", "presentar")
ESCRITURAS = ("abrir", "registrar", "corregir", "presentar")

ROLES_QUE_LEEN_SIN_SER_DE_UN_AREA = (Role.RECTORIA, Role.REVISOR_POA)

ROLES_QUE_NI_LEEN = (Role.CONSULTA,)


@dataclass
class Escenario:
    app: object
    client: object
    ejercicio_id: int
    area_id: int
    planeacion: dict[str, str]
    capturista: dict[str, str]
    poa_area_id: int
    actividad_id: int
    fabrica: async_sessionmaker | None


def _programacion(metas: tuple[Decimal, ...], *, sin_incluir: tuple[int, ...] = ()) -> list[dict]:
    return [
        {
            "mes": mes,
            "meta": str(Decimal(0) if mes in sin_incluir else metas[mes - 1]),
            "incluido": mes not in sin_incluir,
        }
        for mes in range(1, 13)
    ]


async def _version_del_instrumento(escenario: Escenario) -> int:
    if escenario.fabrica is None:
        return next(VERSIONES_EN_MEMORIA)
    async with escenario.fabrica() as sesion:
        instrumento = InstrumentModel(nombre=f"Instrumento del POA del área {uuid4().hex[:8]}")
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


async def _accion_del_pide(escenario: Escenario, *, retirada: bool = False) -> int:
    version = await _version_del_instrumento(escenario)
    creado = await escenario.client.post(
        f"{API}/pide/versiones/{version}/nodos",
        headers=escenario.planeacion,
        json={
            "tipo": "accion",
            "clave": f"A{uuid4().hex[:8]}",
            "denominacion": "Una acción del PIDE",
            "orden": 1,
        },
    )
    assert creado.status_code == 201, creado.text
    nodo_id = creado.json()["id"]
    if retirada:
        retiro = await escenario.client.post(
            f"{API}/pide/nodos/{nodo_id}/desactivar", headers=escenario.planeacion
        )
        assert retiro.status_code == 200, retiro.text
    return nodo_id


async def _unidad_de_medida(escenario: Escenario) -> int:
    listado = await escenario.client.get(
        f"{API}/catalogos/unidades-medida", headers=escenario.planeacion
    )
    assert listado.status_code == 200, listado.text
    return listado.json()[0]["id"]


async def _consultar(escenario: Escenario, cabeceras: dict[str, str] | None = None, **parametros):
    return await escenario.client.get(
        f"{POA_INST}/areas/{escenario.area_id}",
        headers=cabeceras or escenario.planeacion,
        params={"ejercicio_id": escenario.ejercicio_id, **parametros},
    )


async def _abrir(escenario: Escenario, cabeceras: dict[str, str] | None = None):
    return await escenario.client.post(
        f"{POA_INST}/areas/{escenario.area_id}/abrir",
        headers=cabeceras or escenario.planeacion,
        params={"ejercicio_id": escenario.ejercicio_id},
    )


async def _registrar(
    escenario: Escenario, cuerpo: dict, cabeceras: dict[str, str] | None = None, **parametros
):
    return await escenario.client.post(
        f"{POA_INST}/areas/{escenario.area_id}/actividades",
        headers=cabeceras or escenario.planeacion,
        params={"ejercicio_id": escenario.ejercicio_id, **parametros},
        json=cuerpo,
    )


async def _corregir(
    escenario: Escenario,
    actividad_id: int,
    cuerpo: dict,
    cabeceras: dict[str, str] | None = None,
):
    return await escenario.client.patch(
        f"{POA_INST}/areas/{escenario.area_id}/actividades/{actividad_id}",
        headers=cabeceras or escenario.planeacion,
        params={"ejercicio_id": escenario.ejercicio_id},
        json=cuerpo,
    )


async def _presentar(escenario: Escenario, version: int, cabeceras: dict[str, str] | None = None):
    return await escenario.client.post(
        f"{POA_INST}/areas/{escenario.area_id}/presentar",
        headers=cabeceras or escenario.planeacion,
        params={"ejercicio_id": escenario.ejercicio_id},
        json={"version": version},
    )


def _peticion(nombre: str, escenario: Escenario) -> tuple[str, str, dict, dict | None]:
    area = f"{POA_INST}/areas/{escenario.area_id}"
    consulta = {"ejercicio_id": escenario.ejercicio_id}
    return {
        "consultar": ("GET", area, consulta, None),
        "abrir": ("POST", f"{area}/abrir", consulta, None),
        "registrar": (
            "POST",
            f"{area}/actividades",
            consulta,
            {"denominacion": "Una actividad nueva"},
        ),
        "corregir": (
            "PATCH",
            f"{area}/actividades/{escenario.actividad_id}",
            consulta,
            {"version": 1, "denominacion": "Corregida"},
        ),
        "presentar": ("POST", f"{area}/presentar", consulta, {"version": 1}),
    }[nombre]


async def _pedir(escenario: Escenario, nombre: str, cabeceras: dict[str, str] | None):
    metodo, url, parametros, cuerpo = _peticion(nombre, escenario)
    return await escenario.client.request(
        metodo, url, headers=cabeceras, params=parametros, json=cuerpo
    )


async def _releida(escenario: Escenario, actividad_id: int) -> dict:
    listado = await _consultar(escenario, incluir_inactivas=True)
    assert listado.status_code == 200, listado.text
    return next(una for una in listado.json()["actividades"] if una["id"] == actividad_id)


async def _actividad_completa(escenario: Escenario, **campos) -> dict:
    cuerpo = {
        "denominacion": "Impartir el taller de titulación",
        "nodo_id": await _accion_del_pide(escenario),
        "unidad_medida_id": await _unidad_de_medida(escenario),
        "metodo_evaluacion": "Lista de asistencia",
        "meta_anual": "24",
        "programacion": _programacion(DOCE_METAS_QUE_SUMAN_24),
        **campos,
    }
    registrada = await _registrar(escenario, cuerpo)
    assert registrada.status_code == 201, registrada.text
    return registrada.json()


async def _ya_abierto_con_una_actividad(armado: Escenario) -> Escenario:
    abierto = await _abrir(armado)
    assert abierto.status_code == 200, abierto.text
    armado.poa_area_id = abierto.json()["id"]
    registrada = await _registrar(armado, {"denominacion": "La actividad que ya estaba"})
    assert registrada.status_code == 201, registrada.text
    armado.actividad_id = registrada.json()["id"]
    return armado


@pytest.fixture
async def escenario(backend_client, planeacion_headers, area_propia, capturista_de_su_area_headers):
    app, client = backend_client
    anio = await anio_libre(client, planeacion_headers)
    poa = await crear_poa(client, planeacion_headers, anio)
    ejercicio = await crear_ejercicio(client, planeacion_headers, poa, anio)
    armado = Escenario(
        app=app,
        client=client,
        ejercicio_id=ejercicio["id"],
        area_id=area_propia,
        planeacion=planeacion_headers,
        capturista=capturista_de_su_area_headers,
        poa_area_id=0,
        actividad_id=0,
        fabrica=None,
    )
    if app.state.db_engine is None:
        yield await _ya_abierto_con_una_actividad(armado)
        return
    async with app.state.db_engine.connect() as conexion:
        transaccion = await conexion.begin()
        armado.fabrica = async_sessionmaker(
            bind=conexion, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        app.state.poa_area_repository = SqlAlchemyPoaAreaRepository(armado.fabrica)
        app.state.strategic_tree_repository = SqlAlchemyStrategicTreeRepository(armado.fabrica)
        try:
            yield await _ya_abierto_con_una_actividad(armado)
        finally:
            await transaccion.rollback()


@pytest.mark.parametrize("endpoint", ENDPOINTS)
async def test_sin_sesion_el_poa_del_area_contesta_401(escenario, endpoint):
    respuesta = await _pedir(escenario, endpoint, None)

    assert respuesta.status_code == 401, respuesta.text


@pytest.mark.parametrize("endpoint", ENDPOINTS)
async def test_el_capturista_de_otra_area_no_entra_al_poa_de_esta(
    escenario, endpoint, nueva_area, cuenta_con_rol
):
    de_otra_area = await cuenta_con_rol(Role.CAPTURISTA_POA, area_id=await nueva_area())

    respuesta = await _pedir(escenario, endpoint, de_otra_area)

    assert respuesta.status_code == 403, respuesta.text
    assert respuesta.json()["code"] == "FORBIDDEN"


@pytest.mark.parametrize("endpoint", ENDPOINTS)
async def test_quien_no_tiene_area_tampoco_entra_al_poa_de_una(
    escenario, endpoint, capturista_sin_area_headers
):
    respuesta = await _pedir(escenario, endpoint, capturista_sin_area_headers)

    assert respuesta.status_code == 403, respuesta.text


@pytest.mark.parametrize("endpoint", ENDPOINTS)
async def test_el_capturista_de_esta_area_si_entra(escenario, endpoint):
    respuesta = await _pedir(escenario, endpoint, escenario.capturista)

    assert respuesta.status_code != 403, respuesta.text


@pytest.mark.parametrize("endpoint", ENDPOINTS)
async def test_planeacion_entra_a_cualquier_area_aunque_no_tenga_ninguna(escenario, endpoint):
    respuesta = await _pedir(escenario, endpoint, escenario.planeacion)

    assert respuesta.status_code != 403, respuesta.text


@pytest.mark.parametrize("rol", ROLES_QUE_NI_LEEN, ids=lambda rol: rol.value)
@pytest.mark.parametrize("endpoint", ENDPOINTS)
async def test_un_rol_ajeno_a_la_formulacion_no_entra_ni_a_leer(
    escenario, endpoint, rol, cuenta_con_rol
):
    ajeno = await cuenta_con_rol(rol, area_id=escenario.area_id)

    respuesta = await _pedir(escenario, endpoint, ajeno)

    assert respuesta.status_code == 403, respuesta.text


async def test_el_responsable_de_su_area_lee_el_poa_pero_no_lo_escribe(escenario, cuenta_con_rol):
    jefe = await cuenta_con_rol(Role.RESPONSABLE_AREA, area_id=escenario.area_id)

    lectura = await _pedir(escenario, "consultar", jefe)
    escrituras = {
        endpoint: (await _pedir(escenario, endpoint, jefe)).status_code for endpoint in ESCRITURAS
    }

    assert lectura.status_code == 200, lectura.text
    assert escrituras == dict.fromkeys(ESCRITURAS, 403)


@pytest.mark.parametrize("rol", ROLES_QUE_LEEN_SIN_SER_DE_UN_AREA, ids=lambda rol: rol.value)
@pytest.mark.parametrize("area_de_la_cuenta", ["sin_area", "otra_area"])
async def test_quien_dictamina_lee_cualquier_area_y_no_escribe_en_ninguna(
    escenario, cuenta_con_rol, nueva_area, rol, area_de_la_cuenta
):
    suya = None if area_de_la_cuenta == "sin_area" else await nueva_area()
    quien_dictamina = await cuenta_con_rol(rol, area_id=suya)

    lectura = await _pedir(escenario, "consultar", quien_dictamina)
    escrituras = {
        endpoint: (await _pedir(escenario, endpoint, quien_dictamina)).status_code
        for endpoint in ESCRITURAS
    }

    assert lectura.status_code == 200, lectura.text
    assert lectura.json()["area_id"] == escenario.area_id
    assert escrituras == dict.fromkeys(ESCRITURAS, 403)


async def test_el_capturista_formula_el_poa_de_su_area_de_punta_a_punta(escenario):
    leido = await _consultar(escenario, escenario.capturista)
    registrada = await _registrar(
        escenario, {"denominacion": "La que captura el área"}, escenario.capturista
    )
    corregida = await _corregir(
        escenario,
        registrada.json()["id"],
        {"version": 1, "metodo_evaluacion": "Acta de la sesión"},
        escenario.capturista,
    )

    assert leido.status_code == 200, leido.text
    assert leido.json()["area_id"] == escenario.area_id
    assert registrada.status_code == 201, registrada.text
    assert corregida.status_code == 200, corregida.text
    assert corregida.json()["metodo_evaluacion"] == "Acta de la sesión"


async def test_abrir_el_poa_del_area_lo_deja_en_borrador_y_abrirlo_dos_veces_da_el_mismo(
    escenario, nueva_area
):
    propia = Escenario(**{**escenario.__dict__, "area_id": await nueva_area()})

    primera = await _abrir(propia)
    segunda = await _abrir(propia)

    assert primera.status_code == segunda.status_code == 200, primera.text
    assert primera.json()["id"] == segunda.json()["id"]
    assert primera.json()["version"] == segunda.json()["version"] == 1
    assert primera.json()["estado"] == "borrador"
    assert primera.json()["ejercicio_id"] == propia.ejercicio_id
    assert primera.json()["area_id"] == propia.area_id
    assert primera.json()["actividades"] == []


async def test_consultar_un_poa_que_nadie_abrio_no_lo_abre(escenario, nueva_area):
    sin_abrir = Escenario(**{**escenario.__dict__, "area_id": await nueva_area()})

    respuesta = await _consultar(sin_abrir)

    assert respuesta.status_code == 404, respuesta.text
    assert respuesta.json()["code"] == "RESOURCE_NOT_FOUND"
    sigue_sin_abrir = await escenario.app.state.poa_area_repository.find_poa_area(
        sin_abrir.ejercicio_id, sin_abrir.area_id
    )
    assert sigue_sin_abrir is None


async def test_el_poa_del_area_es_uno_por_ejercicio_y_no_uno_por_area(escenario):
    otro_anio = await anio_libre(escenario.client, escenario.planeacion)
    otro_poa = await crear_poa(escenario.client, escenario.planeacion, otro_anio)
    otro = await crear_ejercicio(escenario.client, escenario.planeacion, otro_poa, otro_anio)
    en_el_otro_ejercicio = Escenario(**{**escenario.__dict__, "ejercicio_id": otro["id"]})

    abierto = await _abrir(en_el_otro_ejercicio)

    assert abierto.status_code == 200, abierto.text
    assert abierto.json()["id"] != escenario.poa_area_id
    assert abierto.json()["ejercicio_id"] == otro["id"]
    assert abierto.json()["area_id"] == escenario.area_id
    assert abierto.json()["actividades"] == []
    assert len((await _consultar(escenario)).json()["actividades"]) == 1


async def test_abrir_el_poa_de_un_ejercicio_que_no_existe_se_niega(escenario):
    inventado = Escenario(**{**escenario.__dict__, "ejercicio_id": MAYOR_ENTERO_DE_LA_BASE})

    respuesta = await _abrir(inventado)

    assert respuesta.status_code == 422, respuesta.text
    assert respuesta.json()["code"] == "BUSINESS_VALIDATION_ERROR"
    assert respuesta.json()["message"] == EL_EJERCICIO_POA_NO_EXISTE


async def test_abrir_el_poa_de_un_area_que_no_existe_se_niega(escenario):
    inventada = Escenario(**{**escenario.__dict__, "area_id": MAYOR_ENTERO_DE_LA_BASE})

    respuesta = await _abrir(inventada)

    assert respuesta.status_code == 422, respuesta.text
    assert respuesta.json()["code"] == "BUSINESS_VALIDATION_ERROR"
    assert respuesta.json()["message"] == EL_AREA_NO_EXISTE


async def test_el_poa_que_otro_abrio_a_la_vez_se_devuelve_en_vez_de_chocar(escenario, nueva_area):
    otra_area = await nueva_area()
    repositorio = escenario.app.state.poa_area_repository
    escenario.app.state.poa_area_repository = _ElQueOtroAbrioEnMedio(repositorio)
    escenario.area_id = otra_area

    respuesta = await _abrir(escenario)

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["area_id"] == otra_area
    assert escenario.app.state.poa_area_repository.aperturas == 1


class _ElQueOtroAbrioEnMedio:
    def __init__(self, real) -> None:
        self.real = real
        self.aperturas = 0

    def __getattr__(self, nombre):
        return getattr(self.real, nombre)

    async def add_poa_area(self, poa_area):
        self.aperturas += 1
        await self.real.add_poa_area(poa_area)
        raise ConflictError("El área ya tiene su POA en este ejercicio.")


async def test_registrar_una_actividad_la_deja_en_el_listado_con_su_version(escenario):
    registrada = await _registrar(escenario, {"denominacion": "  Dar el curso de inducción  "})

    listado = await _consultar(escenario)
    assert registrada.status_code == 201, registrada.text
    assert registrada.json()["denominacion"] == "Dar el curso de inducción"
    assert registrada.json()["version"] == 1
    assert registrada.json()["activa"] is True
    assert registrada.json()["programacion"] == []
    cual = next(
        una for una in listado.json()["actividades"] if una["id"] == registrada.json()["id"]
    )
    assert cual["denominacion"] == "Dar el curso de inducción"


async def test_una_actividad_completa_se_guarda_y_se_lee_igual(escenario):
    completa = await _actividad_completa(escenario)

    assert completa["meta_anual"] == "24"
    assert [mes["meta"] for mes in completa["programacion"]] == [
        str(meta) for meta in DOCE_METAS_QUE_SUMAN_24
    ]
    leida = next(
        una
        for una in (await _consultar(escenario)).json()["actividades"]
        if una["id"] == completa["id"]
    )
    assert leida["meta_anual"] == "24"
    assert leida["metodo_evaluacion"] == "Lista de asistencia"
    assert [mes["mes"] for mes in leida["programacion"]] == list(range(1, 13))
    assert [mes["meta"] for mes in leida["programacion"]] == [
        str(meta) for meta in DOCE_METAS_QUE_SUMAN_24
    ]
    assert all(mes["incluido"] for mes in leida["programacion"])


async def test_la_programacion_sale_en_orden_aunque_se_mande_revuelta(escenario):
    al_reves = _programacion(DOCE_METAS_QUE_SUMAN_24)[::-1]

    registrada = await _registrar(
        escenario, {"denominacion": "Con los meses al revés", "programacion": al_reves}
    )

    assert registrada.status_code == 201, registrada.text
    assert [mes["mes"] for mes in registrada.json()["programacion"]] == list(range(1, 13))
    assert [mes["meta"] for mes in registrada.json()["programacion"]] == [
        str(meta) for meta in DOCE_METAS_QUE_SUMAN_24
    ]


async def test_lo_que_el_guardado_parcial_no_manda_no_se_borra(escenario):
    completa = await _actividad_completa(escenario)

    corregida = await _corregir(
        escenario,
        completa["id"],
        {"version": completa["version"], "denominacion": "Con otra denominación"},
    )

    assert corregida.status_code == 200, corregida.text
    despues = corregida.json()
    assert despues["denominacion"] == "Con otra denominación"
    assert despues["nodo_id"] == completa["nodo_id"]
    assert despues["unidad_medida_id"] == completa["unidad_medida_id"]
    assert despues["metodo_evaluacion"] == completa["metodo_evaluacion"]
    assert despues["meta_anual"] == completa["meta_anual"] == "24"
    assert despues["programacion"] == completa["programacion"]
    assert despues["activa"] == completa["activa"]
    assert despues["version"] == completa["version"] + 1
    assert await _releida(escenario, completa["id"]) == despues


async def test_el_nulo_explicito_del_guardado_parcial_si_borra(escenario):
    completa = await _actividad_completa(escenario)

    corregida = await _corregir(
        escenario,
        completa["id"],
        {
            "version": completa["version"],
            "nodo_id": None,
            "unidad_medida_id": None,
            "metodo_evaluacion": None,
            "meta_anual": None,
        },
    )

    assert corregida.status_code == 200, corregida.text
    despues = corregida.json()
    assert despues["nodo_id"] is None
    assert despues["unidad_medida_id"] is None
    assert despues["metodo_evaluacion"] is None
    assert despues["meta_anual"] is None
    assert despues["denominacion"] == completa["denominacion"]
    assert despues["programacion"] == completa["programacion"]
    assert await _releida(escenario, completa["id"]) == despues


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("denominacion", "Otra denominación"),
        ("metodo_evaluacion", "Otro método"),
        ("activa", False),
    ],
)
async def test_el_guardado_parcial_si_cambia_lo_que_le_mandan(escenario, campo, valor):
    completa = await _actividad_completa(escenario)

    corregida = await _corregir(
        escenario, completa["id"], {"version": completa["version"], campo: valor}
    )

    assert corregida.status_code == 200, corregida.text
    assert corregida.json()[campo] == valor
    guardada = next(
        una
        for una in (await _consultar(escenario, incluir_inactivas=True)).json()["actividades"]
        if una["id"] == completa["id"]
    )
    assert guardada[campo] == valor


@pytest.mark.parametrize("campo", ["denominacion", "programacion", "activa"])
async def test_tres_campos_del_guardado_parcial_no_admiten_el_nulo_explicito(escenario, campo):
    completa = await _actividad_completa(escenario)

    corregida = await _corregir(
        escenario, completa["id"], {"version": completa["version"], campo: None}
    )

    assert corregida.status_code == 422, corregida.text
    assert corregida.json()["code"] == "REQUEST_VALIDATION_ERROR"


async def test_el_guardado_parcial_exige_la_version_sobre_la_que_se_edita(escenario):
    completa = await _actividad_completa(escenario)

    sin_version = await _corregir(escenario, completa["id"], {"denominacion": "Sin versión"})

    assert sin_version.status_code == 422, sin_version.text


async def test_guardar_sobre_una_version_vieja_contesta_409(escenario):
    completa = await _actividad_completa(escenario)
    primera = await _corregir(
        escenario, completa["id"], {"version": completa["version"], "denominacion": "La primera"}
    )
    assert primera.status_code == 200, primera.text

    segunda = await _corregir(
        escenario, completa["id"], {"version": completa["version"], "denominacion": "La segunda"}
    )

    assert segunda.status_code == 409, segunda.text
    assert segunda.json()["code"] == "CONFLICT"
    assert (await _consultar(escenario)).json()["actividades"] != []


async def test_una_actividad_de_otro_poa_no_se_corrige_desde_este(escenario, nueva_area):
    ajena = Escenario(**{**escenario.__dict__, "area_id": await nueva_area()})
    abierto = await _abrir(ajena)
    assert abierto.status_code == 200, abierto.text
    suya = await _registrar(ajena, {"denominacion": "La actividad del área vecina"})
    assert suya.status_code == 201, suya.text

    desde_este = await _corregir(
        escenario, suya.json()["id"], {"version": 1, "denominacion": "Robada"}
    )

    assert desde_este.status_code == 404, desde_este.text
    assert desde_este.json()["code"] == "RESOURCE_NOT_FOUND"


async def test_una_actividad_no_cuelga_de_un_nodo_retirado_del_pide(escenario):
    retirada = await _accion_del_pide(escenario, retirada=True)

    respuesta = await _registrar(
        escenario, {"denominacion": "Con una acción retirada", "nodo_id": retirada}
    )

    assert respuesta.status_code == 422, respuesta.text
    assert respuesta.json()["code"] == "BUSINESS_VALIDATION_ERROR"
    assert "retirado del PIDE" in respuesta.json()["message"]


async def test_una_actividad_no_cuelga_de_un_nodo_que_no_es_accion(escenario):
    version = await _version_del_instrumento(escenario)
    creado = await escenario.client.post(
        f"{API}/pide/versiones/{version}/nodos",
        headers=escenario.planeacion,
        json={
            "tipo": "eje",
            "clave": f"E{uuid4().hex[:8]}",
            "denominacion": "Un eje del PIDE",
            "orden": 1,
        },
    )
    assert creado.status_code == 201, creado.text

    respuesta = await _registrar(
        escenario, {"denominacion": "Colgada de un eje", "nodo_id": creado.json()["id"]}
    )

    assert respuesta.status_code == 422, respuesta.text
    assert "nivel" in respuesta.json()["message"]


async def test_las_actividades_retiradas_no_salen_salvo_que_se_pidan(escenario):
    completa = await _actividad_completa(escenario)
    retirada = await _corregir(
        escenario, completa["id"], {"version": completa["version"], "activa": False}
    )
    assert retirada.status_code == 200, retirada.text

    sin_pedirlas = await _consultar(escenario)
    pidiendolas = await _consultar(escenario, incluir_inactivas=True)
    reabierto = await _abrir(escenario)

    assert completa["id"] not in [una["id"] for una in sin_pedirlas.json()["actividades"]]
    assert completa["id"] in [una["id"] for una in pidiendolas.json()["actividades"]]
    assert (
        next(una for una in pidiendolas.json()["actividades"] if una["id"] == completa["id"])[
            "activa"
        ]
        is False
    )
    assert reabierto.status_code == 200, reabierto.text
    assert reabierto.json()["actividades"] == sin_pedirlas.json()["actividades"]


async def test_presentar_un_poa_sin_responsable_de_area_lo_dice(escenario):
    await _actividad_completa(escenario)
    retirar = await _corregir(escenario, escenario.actividad_id, {"version": 1, "activa": False})
    assert retirar.status_code == 200, retirar.text

    respuesta = await _presentar(escenario, 1)

    assert respuesta.status_code == 422, respuesta.text
    assert respuesta.json()["code"] == "BUSINESS_VALIDATION_ERROR"
    assert "no tiene responsable asignado" in respuesta.json()["message"]


async def test_presentar_un_poa_incompleto_dice_que_le_falta_a_cada_actividad(
    escenario, cuenta_con_rol
):
    await cuenta_con_rol(Role.RESPONSABLE_AREA, area_id=escenario.area_id)

    respuesta = await _presentar(escenario, 1)

    assert respuesta.status_code == 422, respuesta.text
    assert "La actividad que ya estaba" in respuesta.json()["message"]
    assert "la unidad de medida" in respuesta.json()["message"]
    assert (await _consultar(escenario)).json()["estado"] == "borrador"


async def test_presentar_lo_deja_enviado_y_ya_no_admite_cambios(escenario, cuenta_con_rol):
    await cuenta_con_rol(Role.RESPONSABLE_AREA, area_id=escenario.area_id)
    completa = await _actividad_completa(escenario)
    retirar = await _corregir(escenario, escenario.actividad_id, {"version": 1, "activa": False})
    assert retirar.status_code == 200, retirar.text

    enviado = await _presentar(escenario, 1)

    assert enviado.status_code == 200, enviado.text
    assert enviado.json()["estado"] == "enviado"
    assert enviado.json()["version"] == 2
    assert [una["id"] for una in enviado.json()["actividades"]] == [completa["id"]]
    assert enviado.json()["actividades"] == (await _consultar(escenario)).json()["actividades"]
    assert (await _consultar(escenario)).json()["estado"] == "enviado"
    otra = await _registrar(escenario, {"denominacion": "Después de enviar"})
    corregir = await _corregir(
        escenario, completa["id"], {"version": completa["version"], "denominacion": "Tarde"}
    )
    reenviar = await _presentar(escenario, 2)
    assert [otra.status_code, corregir.status_code, reenviar.status_code] == [422, 422, 422]
    assert otra.json()["code"] == "INVALID_STATE"
    assert corregir.json()["code"] == "INVALID_STATE"
    assert reenviar.json()["code"] == "INVALID_STATE"


async def test_presentar_sobre_una_version_vieja_del_poa_contesta_409(escenario, cuenta_con_rol):
    await cuenta_con_rol(Role.RESPONSABLE_AREA, area_id=escenario.area_id)
    await _actividad_completa(escenario)
    retirar = await _corregir(escenario, escenario.actividad_id, {"version": 1, "activa": False})
    assert retirar.status_code == 200, retirar.text

    respuesta = await _presentar(escenario, 2)

    assert respuesta.status_code == 409, respuesta.text
    assert respuesta.json()["code"] == "CONFLICT"
    assert (await _consultar(escenario)).json()["estado"] == "borrador"


@pytest.mark.parametrize("endpoint", ["consultar", "registrar", "corregir", "presentar"])
async def test_sin_el_poa_abierto_las_escrituras_contestan_404(escenario, endpoint, nueva_area):
    sin_abrir = Escenario(**{**escenario.__dict__, "area_id": await nueva_area()})

    respuesta = await _pedir(sin_abrir, endpoint, escenario.planeacion)

    assert respuesta.status_code == 404, respuesta.text
    assert respuesta.json()["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.parametrize("endpoint", ENDPOINTS)
async def test_el_ejercicio_es_obligatorio_en_los_cinco(escenario, endpoint):
    metodo, url, _, cuerpo = _peticion(endpoint, escenario)

    respuesta = await escenario.client.request(
        metodo, url, headers=escenario.planeacion, json=cuerpo
    )

    assert respuesta.status_code == 422, respuesta.text


async def test_la_programacion_incompleta_no_se_guarda(escenario):
    once_meses = _programacion(DOCE_METAS_QUE_SUMAN_24)[:11]

    respuesta = await _registrar(
        escenario, {"denominacion": "Con once meses", "programacion": once_meses}
    )

    assert respuesta.status_code == 422, respuesta.text
    assert respuesta.json()["code"] == "BUSINESS_VALIDATION_ERROR"
    assert "los doce meses del ejercicio" in respuesta.json()["message"]


async def test_un_mes_fuera_de_la_programacion_con_meta_no_se_guarda(escenario):
    con_meta_y_fuera = _programacion(DOCE_METAS_QUE_SUMAN_24)
    con_meta_y_fuera[4]["incluido"] = False

    respuesta = await _registrar(
        escenario, {"denominacion": "Con un mes fuera y con meta", "programacion": con_meta_y_fuera}
    )

    assert respuesta.status_code == 422, respuesta.text
    assert "queda fuera de la programación" in respuesta.json()["message"]


async def test_una_meta_negativa_no_se_guarda(escenario):
    respuesta = await _registrar(
        escenario, {"denominacion": "Con meta negativa", "meta_anual": "-1"}
    )

    assert respuesta.status_code == 422, respuesta.text


async def test_un_mes_fuera_de_la_programacion_se_guarda_y_se_lee_fuera(escenario):
    sin_el_quinto = _programacion(DOCE_METAS_QUE_SUMAN_24, sin_incluir=(5,))

    completa = await _actividad_completa(escenario, meta_anual="19", programacion=sin_el_quinto)

    leida = await _releida(escenario, completa["id"])
    por_mes = {mes["mes"]: mes for mes in leida["programacion"]}
    assert por_mes[5] == {"mes": 5, "meta": "0", "incluido": False}
    assert por_mes[3] == {"mes": 3, "meta": "0", "incluido": True}
    assert por_mes[4] == {"mes": 4, "meta": "2", "incluido": True}
    assert [mes["mes"] for mes in leida["programacion"] if not mes["incluido"]] == [5]
    assert leida["meta_anual"] == "19"
    assert leida["falta_para_presentar"] == []
    assert leida["programacion"] == completa["programacion"]


async def test_la_respuesta_dice_que_le_falta_a_cada_actividad(escenario):
    completa = await _actividad_completa(escenario)
    con_la_suma_mal = await _actividad_completa(escenario, meta_anual="25")

    leidas = {una["id"]: una for una in (await _consultar(escenario)).json()["actividades"]}

    assert leidas[completa["id"]]["falta_para_presentar"] == []
    assert leidas[con_la_suma_mal["id"]]["falta_para_presentar"] == [
        "que sus meses incluidos en la programación sumen la meta anual: suman 24 de 25"
    ]
    assert leidas[escenario.actividad_id]["falta_para_presentar"] == [
        "la acción del PIDE a la que responde",
        "la unidad de medida",
        "el método de evaluación",
        "la meta anual",
        "la programación de los doce meses (trae 0)",
    ]


async def test_la_respuesta_dice_que_le_falta_al_poa_y_no_solo_a_sus_actividades(escenario):
    leido = await _consultar(escenario)

    intento = await _presentar(escenario, 1)

    faltas = leido.json()["falta_para_presentar"]
    assert any("no tiene responsable asignado" in razon for razon in faltas), faltas
    assert any("1 actividad está incompleta" in razon for razon in faltas), faltas
    assert intento.status_code == 422, intento.text
    assert intento.json()["message"] == EL_POA_DEL_AREA_NO_SE_PUEDE_ENVIAR + " ".join(faltas)


async def test_cuando_al_poa_no_le_falta_nada_se_presenta(escenario, cuenta_con_rol):
    await cuenta_con_rol(Role.RESPONSABLE_AREA, area_id=escenario.area_id)
    await _actividad_completa(escenario)
    retirar = await _corregir(escenario, escenario.actividad_id, {"version": 1, "activa": False})
    assert retirar.status_code == 200, retirar.text

    antes = await _consultar(escenario)
    enviado = await _presentar(escenario, 1)

    assert antes.json()["falta_para_presentar"] == []
    assert enviado.status_code == 200, enviado.text
    assert enviado.json()["falta_para_presentar"] == []


async def test_un_guardado_parcial_sin_campos_no_consume_la_version(escenario):
    completa = await _actividad_completa(escenario)

    sin_campos = await _corregir(escenario, completa["id"], {"version": completa["version"]})
    y_despues = await _corregir(
        escenario, completa["id"], {"version": completa["version"], "denominacion": "Ahora sí"}
    )

    assert sin_campos.status_code == 200, sin_campos.text
    assert sin_campos.json() == completa
    assert await _releida(escenario, completa["id"]) == y_despues.json()
    assert y_despues.status_code == 200, y_despues.text
    assert y_despues.json()["version"] == completa["version"] + 1


async def test_un_guardado_parcial_sin_campos_sobre_una_version_vieja_contesta_409(escenario):
    completa = await _actividad_completa(escenario)
    primera = await _corregir(
        escenario, completa["id"], {"version": completa["version"], "denominacion": "La primera"}
    )
    assert primera.status_code == 200, primera.text

    sin_campos = await _corregir(escenario, completa["id"], {"version": completa["version"]})

    assert sin_campos.status_code == 409, sin_campos.text
    assert sin_campos.json()["code"] == "CONFLICT"


async def test_el_guardado_parcial_no_mueve_la_actividad_a_un_nodo_retirado(escenario):
    completa = await _actividad_completa(escenario)
    retirada = await _accion_del_pide(escenario, retirada=True)

    corregida = await _corregir(
        escenario, completa["id"], {"version": completa["version"], "nodo_id": retirada}
    )

    assert corregida.status_code == 422, corregida.text
    assert corregida.json()["code"] == "BUSINESS_VALIDATION_ERROR"
    assert "retirado del PIDE" in corregida.json()["message"]
    leida = await _releida(escenario, completa["id"])
    assert leida["nodo_id"] == completa["nodo_id"]
    assert leida["version"] == completa["version"]


@pytest.mark.parametrize(
    "campo,tipo",
    [("denominacion", "string"), ("programacion", "array"), ("activa", "boolean")],
)
async def test_el_esquema_del_patch_y_el_servidor_dicen_lo_mismo_del_nulo(escenario, campo, tipo):
    publicado = escenario.app.openapi()["components"]["schemas"]["ActualizarActividadRequest"][
        "properties"
    ][campo]
    completa = await _actividad_completa(escenario)

    con_nulo = await _corregir(
        escenario, completa["id"], {"version": completa["version"], campo: None}
    )

    assert "anyOf" not in publicado, publicado
    assert publicado["type"] == tipo, publicado
    assert "default" not in publicado, publicado
    assert con_nulo.status_code == 422, con_nulo.text
    assert con_nulo.json()["code"] == "REQUEST_VALIDATION_ERROR"
    assert EL_NULO_NO_ES_LEGAL_AQUI in con_nulo.text


async def test_el_esquema_del_patch_si_publica_el_nulo_donde_el_servidor_lo_acepta(escenario):
    publicado = escenario.app.openapi()["components"]["schemas"]["ActualizarActividadRequest"][
        "properties"
    ]
    completa = await _actividad_completa(escenario)

    con_nulo = await _corregir(
        escenario,
        completa["id"],
        {"version": completa["version"], "nodo_id": None, "meta_anual": None},
    )

    for campo in ("nodo_id", "unidad_medida_id", "metodo_evaluacion", "meta_anual"):
        assert {"type": "null"} in publicado[campo]["anyOf"], campo
    assert con_nulo.status_code == 200, con_nulo.text
    assert con_nulo.json()["nodo_id"] is None
    assert con_nulo.json()["meta_anual"] is None


def test_el_poa_del_area_declara_su_contrato_en_el_openapi(app):
    esquema = app.openapi()
    area = f"{POA_INST}/areas/{{area_id}}"

    operaciones = {
        "consultar": esquema["paths"][area]["get"],
        "abrir": esquema["paths"][f"{area}/abrir"]["post"],
        "registrar": esquema["paths"][f"{area}/actividades"]["post"],
        "corregir": esquema["paths"][f"{area}/actividades/{{actividad_id}}"]["patch"],
        "presentar": esquema["paths"][f"{area}/presentar"]["post"],
    }

    for nombre, operacion in operaciones.items():
        obligatorios = {
            parametro["name"]
            for parametro in operacion["parameters"]
            if parametro["required"] and parametro["in"] == "query"
        }
        assert obligatorios == {"ejercicio_id"}, nombre
        assert operacion["security"] != [], nombre
        assert {"401", "403", "409", "422", "500", "503"} <= set(operacion["responses"]), nombre
        assert ("404" in operacion["responses"]) == (nombre != "abrir"), nombre
