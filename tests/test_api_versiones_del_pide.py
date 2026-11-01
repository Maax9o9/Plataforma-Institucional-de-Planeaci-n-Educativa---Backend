from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.app_factory import create_app
from app.core.config import Settings
from app.modules.identity_access.domain.value_objects import Role
from app.modules.institutional_catalogs.domain.entities import Instrument, InstrumentVersion
from app.modules.institutional_catalogs.infrastructure.sql_repository import (
    SqlAlchemyInstrumentRepository,
    SqlAlchemyInstrumentVersionRepository,
)

PIDE = "/api/v1/pide"
VERSIONES = f"{PIDE}/versiones"
INSTRUMENTO_INEXISTENTE = 10**9
ENTERO_MAS_GRANDE_QUE_CABE = 2**31 - 1
ENTERO_MAS_GRANDE_QUE_LA_BASE = 2**31
ENTERO_MAS_CHICO_QUE_LA_BASE = -(2**31) - 1

CAMPOS_DE_LA_VERSION = {
    "id",
    "instrumento_id",
    "etiqueta",
    "vigente_desde",
    "publicada_en",
    "origen",
}


@dataclass
class Catalogo:
    app: object
    client: object
    cabeceras: dict[str, str]


@pytest.fixture
async def catalogo(backend_client, cuenta_con_rol):
    app, client = backend_client
    cabeceras = await cuenta_con_rol(Role.PLANEACION, area_id=None)
    if app.state.db_engine is None:
        yield Catalogo(app=app, client=client, cabeceras=cabeceras)
        return
    async with app.state.db_engine.connect() as conexion:
        transaccion = await conexion.begin()
        fabrica = async_sessionmaker(
            bind=conexion, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        app.state.instrument_repository = SqlAlchemyInstrumentRepository(fabrica)
        app.state.instrument_version_repository = SqlAlchemyInstrumentVersionRepository(fabrica)
        try:
            yield Catalogo(app=app, client=client, cabeceras=cabeceras)
        finally:
            await transaccion.rollback()


async def _instrumento(catalogo: Catalogo) -> int:
    instrumento = Instrument.create(
        code=f"PIDE-{uuid4().hex[:8]}", name=f"Instrumento de prueba {uuid4().hex[:8]}"
    )
    await catalogo.app.state.instrument_repository.add(instrumento)
    return instrumento.id


async def _version(
    catalogo: Catalogo,
    instrumento_id: int,
    etiqueta: str,
    vigente_desde: date,
    *,
    publicada_en: datetime | None = None,
    origen: str | None = None,
) -> int:
    version = InstrumentVersion.create(
        instrument_id=instrumento_id,
        label=etiqueta,
        effective_from=vigente_desde,
        origin=origen,
    )
    version.published_at = publicada_en
    await catalogo.app.state.instrument_version_repository.add(version)
    return version.id


async def _listar(catalogo: Catalogo, **parametros) -> list[dict]:
    respuesta = await catalogo.client.get(VERSIONES, headers=catalogo.cabeceras, params=parametros)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


async def test_las_versiones_llegan_agrupadas_por_instrumento_y_de_la_mas_reciente_a_la_mas_vieja(
    catalogo,
):
    primero = await _instrumento(catalogo)
    segundo = await _instrumento(catalogo)
    vieja = await _version(catalogo, primero, "2019-2024", date(2019, 1, 1))
    reciente = await _version(catalogo, primero, "2025-2030", date(2025, 1, 1))
    empatada = await _version(catalogo, primero, "2025-2030 corregida", date(2025, 1, 1))
    del_segundo = await _version(catalogo, segundo, "2025-2030", date(2025, 1, 1))

    listado = await _listar(catalogo)

    mios = {primero, segundo}
    assert [version["id"] for version in listado if version["instrumento_id"] in mios] == [
        empatada,
        reciente,
        vieja,
        del_segundo,
    ]


async def test_el_filtro_por_instrumento_deja_fuera_las_versiones_de_los_demas(catalogo):
    primero = await _instrumento(catalogo)
    segundo = await _instrumento(catalogo)
    vieja = await _version(catalogo, primero, "2019-2024", date(2019, 1, 1))
    reciente = await _version(catalogo, primero, "2025-2030", date(2025, 1, 1))
    await _version(catalogo, segundo, "2025-2030", date(2025, 1, 1))

    listado = await _listar(catalogo, instrumento_id=primero)

    assert [version["id"] for version in listado] == [reciente, vieja]


@pytest.mark.parametrize("cual", ["sin_versiones", "inexistente"])
async def test_un_instrumento_sin_versiones_contesta_200_con_la_lista_vacia(catalogo, cual):
    con_versiones = await _instrumento(catalogo)
    await _version(catalogo, con_versiones, "2025-2030", date(2025, 1, 1))
    instrumento_id = (
        await _instrumento(catalogo) if cual == "sin_versiones" else INSTRUMENTO_INEXISTENTE
    )

    respuesta = await catalogo.client.get(
        VERSIONES, headers=catalogo.cabeceras, params={"instrumento_id": instrumento_id}
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == []


async def test_cada_version_llega_con_sus_seis_campos(catalogo):
    instrumento = await _instrumento(catalogo)
    publicada_en = datetime(2025, 3, 1, 12, 30, tzinfo=UTC)
    publicada = await _version(
        catalogo,
        instrumento,
        "2025-2030",
        date(2025, 1, 1),
        publicada_en=publicada_en,
        origen="Acuerdo del Consejo Directivo",
    )
    en_borrador = await _version(catalogo, instrumento, "2031-2036", date(2031, 1, 1))

    listado = await _listar(catalogo, instrumento_id=instrumento)

    assert listado[0] == {
        "id": en_borrador,
        "instrumento_id": instrumento,
        "etiqueta": "2031-2036",
        "vigente_desde": "2031-01-01",
        "publicada_en": None,
        "origen": None,
    }
    assert set(listado[1]) == CAMPOS_DE_LA_VERSION
    assert listado[1]["id"] == publicada
    assert listado[1]["etiqueta"] == "2025-2030"
    assert listado[1]["vigente_desde"] == "2025-01-01"
    assert listado[1]["origen"] == "Acuerdo del Consejo Directivo"
    assert datetime.fromisoformat(listado[1]["publicada_en"]) == publicada_en


async def test_sin_sesion_el_listado_de_versiones_contesta_401(catalogo):
    instrumento = await _instrumento(catalogo)
    await _version(catalogo, instrumento, "2025-2030", date(2025, 1, 1))

    respuesta = await catalogo.client.get(VERSIONES)

    assert respuesta.status_code == 401, respuesta.text


@pytest.mark.parametrize("rol", list(Role), ids=lambda rol: rol.value)
async def test_cualquier_rol_autenticado_lee_las_versiones(catalogo, cuenta_con_rol, rol):
    instrumento = await _instrumento(catalogo)
    version = await _version(catalogo, instrumento, "2025-2030", date(2025, 1, 1))
    cabeceras = await cuenta_con_rol(rol, area_id=None)

    respuesta = await catalogo.client.get(
        VERSIONES, headers=cabeceras, params={"instrumento_id": instrumento}
    )

    assert respuesta.status_code == 200, respuesta.text
    assert [devuelta["id"] for devuelta in respuesta.json()] == [version]


@pytest.mark.parametrize(
    "instrumento_id",
    [ENTERO_MAS_GRANDE_QUE_LA_BASE, ENTERO_MAS_CHICO_QUE_LA_BASE, 0, "once"],
    ids=["mas_grande_que_la_base", "mas_chico_que_la_base", "cero", "no_es_un_entero"],
)
async def test_un_instrumento_que_no_cabe_en_el_entero_de_la_base_se_rechaza(
    catalogo, instrumento_id
):
    respuesta = await catalogo.client.get(
        VERSIONES, headers=catalogo.cabeceras, params={"instrumento_id": instrumento_id}
    )

    assert respuesta.status_code == 422, respuesta.text
    assert respuesta.json()["code"] == "REQUEST_VALIDATION_ERROR"


async def test_el_entero_mas_grande_que_cabe_en_la_base_se_acepta(catalogo):
    assert await _listar(catalogo, instrumento_id=ENTERO_MAS_GRANDE_QUE_CABE) == []


def test_el_openapi_publica_el_listado_con_sus_seis_campos_y_el_filtro_opcional():
    esquema = create_app(
        Settings(
            environment="testing",
            secret_key="test-secret-key-with-more-than-32-characters",
            database_url=None,
            email_provider="console",
        )
    ).openapi()
    operacion = esquema["paths"][VERSIONES]

    assert set(operacion) == {"get"}
    assert [
        (parametro["name"], parametro["in"], parametro["required"])
        for parametro in operacion["get"]["parameters"]
    ] == [("instrumento_id", "query", False)]
    version = esquema["components"]["schemas"]["VersionRespuesta"]
    assert set(version["required"]) == CAMPOS_DE_LA_VERSION
    assert set(version["properties"]) == CAMPOS_DE_LA_VERSION
    assert {"type": "null"} in version["properties"]["publicada_en"]["anyOf"]
    assert {"type": "null"} in version["properties"]["origen"]["anyOf"]
