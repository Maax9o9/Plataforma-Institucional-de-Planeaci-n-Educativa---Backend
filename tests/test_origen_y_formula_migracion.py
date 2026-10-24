from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

RAIZ = Path(__file__).resolve().parents[1]

FORMULA_COMO_LA_IMPRIME_EL_PIDE = (
    "(Nº de estudiantes atendidos por el Programa Institucional de Tutorías / "
    "Nº total de estudiantes inscritos) × 100"
)


@pytest.fixture
async def conexion():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL no configurada")
    motor = create_async_engine(url)
    try:
        async with motor.connect() as abierta:
            transaccion = await abierta.begin()
            try:
                yield abierta
            finally:
                await transaccion.rollback()
    finally:
        await motor.dispose()


async def _version(conexion: AsyncConnection, origen: str | None = None) -> int:
    instrumento = (
        await conexion.execute(
            text("INSERT INTO instrumentos (nombre) VALUES (:nombre) RETURNING id"),
            {"nombre": f"Instrumento de prueba {uuid4().hex[:8]}"},
        )
    ).scalar_one()
    return (
        await conexion.execute(
            text(
                "INSERT INTO instrumento_versiones "
                "(instrumento_id, etiqueta, vigente_desde, origen) "
                "VALUES (:instrumento, 'V1', '2025-01-01', :origen) RETURNING id"
            ),
            {"instrumento": instrumento, "origen": origen},
        )
    ).scalar_one()


async def _nodo(
    conexion: AsyncConnection,
    version: int,
    clave: str,
    tipo: str = "eje",
    formula: str | None = None,
) -> int:
    return (
        await conexion.execute(
            text(
                "INSERT INTO nodos_estrategicos "
                "(version_id, padre_id, tipo, clave, denominacion, orden, formula_indicador) "
                "VALUES (:version, NULL, :tipo, :clave, :denominacion, 1, :formula) RETURNING id"
            ),
            {
                "version": version,
                "tipo": tipo,
                "clave": clave,
                "denominacion": f"Denominacion de {clave}",
                "formula": formula,
            },
        )
    ).scalar_one()


@pytest.mark.asyncio
async def test_las_dos_columnas_existen_y_admiten_nulo(conexion):
    nulables = {
        (tabla, columna): es
        for tabla, columna, es in (
            await conexion.execute(
                text(
                    "SELECT table_name, column_name, is_nullable "
                    "FROM information_schema.columns WHERE table_schema = 'public' "
                    "AND (table_name, column_name) IN "
                    "(('instrumento_versiones', 'origen'), "
                    " ('nodos_estrategicos', 'formula_indicador'))"
                )
            )
        ).all()
    }

    assert nulables == {
        ("instrumento_versiones", "origen"): "YES",
        ("nodos_estrategicos", "formula_indicador"): "YES",
    }


@pytest.mark.asyncio
async def test_el_origen_y_la_formula_guardan_el_texto_entero(conexion):
    version = await _version(conexion, origen="Cargada del PDF del PIDE 2025-2030, capítulo VII")
    accion = await _nodo(
        conexion, version, "1.1.1.1.1", "accion", formula=FORMULA_COMO_LA_IMPRIME_EL_PIDE
    )
    sin_formula = await _nodo(conexion, version, "1")

    guardado = (
        await conexion.execute(
            text(
                "SELECT v.origen, n.formula_indicador, n.denominacion "
                "FROM instrumento_versiones v JOIN nodos_estrategicos n ON n.version_id = v.id "
                "WHERE n.id = :nodo"
            ),
            {"nodo": accion},
        )
    ).one()
    assert guardado.origen == "Cargada del PDF del PIDE 2025-2030, capítulo VII"
    assert guardado.formula_indicador == FORMULA_COMO_LA_IMPRIME_EL_PIDE
    assert guardado.denominacion == "Denominacion de 1.1.1.1.1"

    sin_medida = (
        await conexion.execute(
            text("SELECT formula_indicador FROM nodos_estrategicos WHERE id = :nodo"),
            {"nodo": sin_formula},
        )
    ).scalar_one()
    assert sin_medida is None


@pytest.mark.asyncio
async def test_la_0039_se_baja_con_filas_que_no_usan_las_columnas_nuevas(conexion):
    version = await _version(conexion)
    await _nodo(conexion, version, "1")

    await _bajar_la_0039(conexion)
    assert await _existe_la_columna(conexion, "nodos_estrategicos", "formula_indicador") == 0
    assert await _existe_la_columna(conexion, "instrumento_versiones", "origen") == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("cual", ["origen", "formula"])
async def test_la_0039_se_para_en_cuanto_hay_un_valor(conexion, cual):
    version = await _version(conexion, origen="De algun lado" if cual == "origen" else None)
    await _nodo(
        conexion,
        version,
        "1",
        formula=FORMULA_COMO_LA_IMPRIME_EL_PIDE if cual == "formula" else None,
    )

    esperado = "instrumento_versiones.origen" if cual == "origen" else "formula_indicador"
    with pytest.raises(RuntimeError, match=esperado):
        await _bajar_la_0039(conexion)

    assert await _existe_la_columna(conexion, "nodos_estrategicos", "formula_indicador") == 1
    assert await _existe_la_columna(conexion, "instrumento_versiones", "origen") == 1


LO_QUE_CUELGA_DE_LAS_COLUMNAS_DE_LA_0039 = {
    "una_vista_sobre_la_formula": (
        "CREATE VIEW sonda_formulas AS SELECT formula_indicador FROM nodos_estrategicos",
        "cannot drop column formula_indicador of table nodos_estrategicos",
    ),
    "una_vista_sobre_el_origen": (
        "CREATE VIEW sonda_origenes AS SELECT origen FROM instrumento_versiones",
        "cannot drop column origen of table instrumento_versiones",
    ),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("cuelga", list(LO_QUE_CUELGA_DE_LAS_COLUMNAS_DE_LA_0039))
async def test_la_0039_no_se_baja_llevandose_lo_que_cuelga_de_sus_columnas(conexion, cuelga):
    crear, se_queja_de = LO_QUE_CUELGA_DE_LAS_COLUMNAS_DE_LA_0039[cuelga]
    await conexion.execute(text(crear))
    intento = await conexion.begin_nested()

    with pytest.raises(DBAPIError, match=se_queja_de):
        await _bajar_la_0039(conexion)

    await intento.rollback()
    assert (
        await conexion.execute(text("SELECT count(*) FROM pg_views WHERE viewname LIKE 'sonda%'"))
    ).scalar_one() == 1
    assert await _existe_la_columna(conexion, "nodos_estrategicos", "formula_indicador") == 1
    assert await _existe_la_columna(conexion, "instrumento_versiones", "origen") == 1


async def _existe_la_columna(conexion: AsyncConnection, tabla: str, columna: str) -> int:
    return (
        await conexion.execute(
            text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_name = :tabla AND column_name = :columna"
            ),
            {"tabla": tabla, "columna": columna},
        )
    ).scalar_one()


async def _bajar_la_0039(conexion: AsyncConnection) -> None:
    modulo = (
        ScriptDirectory.from_config(Config(str(RAIZ / "alembic.ini")))
        .get_revision("0039_origen_y_formula")
        .module
    )

    def correr(sincrona) -> None:
        with Operations.context(MigrationContext.configure(sincrona)):
            modulo.downgrade()

    await conexion.run_sync(correr)
