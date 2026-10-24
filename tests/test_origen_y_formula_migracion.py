"""Las dos columnas de la 0039: el origen de una version y la formula de una accion.

Solo corre contra PostgreSQL, por lo mismo que la prueba de la 0038: la
migracion es SQL crudo y el repositorio en memoria no la ejecuta.

Lo que se vigila es lo que la carga del PIDE (tarea 4) va a dar por cierto: que
las dos columnas existen, que admiten NULL -el origen no siempre se sabe y solo
las acciones traen formula- y que guardan el texto entero, que en el caso de la
formula es un parrafo con simbolos y no una etiqueta. Y que bajar la migracion
con algo escrito se niega: la formula vive en el PDF y el origen en la cabeza
de quien cargo, asi que borrarlas no tiene vuelta.
"""

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
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

RAIZ = Path(__file__).resolve().parents[1]

#: La formula tal como el capitulo VII la imprime: no es una expresion que el
#: sistema evalue, es lo que el documento dice.
FORMULA = (
    "(Nº de estudiantes atendidos por el Programa Institucional de Tutorías / "
    "Nº total de estudiantes inscritos) × 100"
)


@pytest.fixture
async def conexion():
    """Conexion cuya transaccion se revierte siempre, como en la prueba de la 0038."""
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
    """Admitir NULL es la mitad del contrato y la que se olvida: el origen de
    una version cargada a mano puede no saberse, y la formula solo la traen las
    acciones -un eje o un objetivo no se miden-. Con las columnas NOT NULL, la
    carga del PIDE tendria que inventar un origen y una formula para cada eje.
    """
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
    """La formula del capitulo VII es un parrafo con simbolos («Nº», «×», «/»),
    no una etiqueta: una columna corta la cortaria y la medida quedaria mal sin
    que nadie lo viera. Las dos son TEXT y se comprueba leyendo lo guardado, no
    lo que se mando.

    La denominacion del nodo lleva otro texto a proposito: si la formula
    acabara en `denominacion` -que es donde iria si no existiera esta columna-
    la lectura lo diria.
    """
    version = await _version(conexion, origen="Cargada del PDF del PIDE 2025-2030, capítulo VII")
    accion = await _nodo(conexion, version, "1.1.1.1.1", "accion", formula=FORMULA)
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
    assert guardado.formula_indicador == FORMULA
    assert guardado.denominacion == "Denominacion de 1.1.1.1.1"

    sin_medida = (
        await conexion.execute(
            text("SELECT formula_indicador FROM nodos_estrategicos WHERE id = :nodo"),
            {"nodo": sin_formula},
        )
    ).scalar_one()
    assert sin_medida is None


@pytest.mark.asyncio
async def test_la_0039_no_se_baja_con_origenes_ni_formulas_escritos(conexion):
    """La 0039 no se lleva una tabla sino dos columnas, asi que lo que cuenta
    no son las filas sino los valores: una version sin origen y un nodo sin
    formula no pierden nada al bajar, y negarse ahi seria negarse por
    costumbre. Con un solo valor escrito, bajar lo borra y no hay donde volver
    a ponerlo -la formula vive en el PDF y el origen en la cabeza de quien
    cargo-.

    Las dos mitades estan medidas: una guarda que contara filas se caeria en la
    primera, y una que no contara nada, en la segunda.
    """
    version = await _version(conexion)
    await _nodo(conexion, version, "1")

    # Sin nada escrito en las columnas nuevas: baja, y el DDL se revierte con
    # la transaccion de la fixture.
    await _bajar_la_0039(conexion)
    assert await _existe_la_columna(conexion, "nodos_estrategicos", "formula_indicador") == 0
    assert await _existe_la_columna(conexion, "instrumento_versiones", "origen") == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("cual", ["origen", "formula"])
async def test_la_0039_se_para_en_cuanto_hay_un_valor(conexion, cual):
    """Una por una: una guarda que mirara solo una de las dos columnas pasaria
    la otra sin que nada lo dijera."""
    version = await _version(conexion, origen="De algun lado" if cual == "origen" else None)
    await _nodo(conexion, version, "1", formula=FORMULA if cual == "formula" else None)

    esperado = "instrumento_versiones.origen" if cual == "origen" else "formula_indicador"
    with pytest.raises(RuntimeError, match=esperado):
        await _bajar_la_0039(conexion)

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
    """Corre el `downgrade` de verdad, con el `op` que Alembic usaria apuntando
    a la conexion de la prueba. Cambiar el cuerpo por `pass` tiene que hacer
    fallar esto."""
    modulo = (
        ScriptDirectory.from_config(Config(str(RAIZ / "alembic.ini")))
        .get_revision("0039_origen_y_formula")
        .module
    )

    def correr(sincrona) -> None:
        with Operations.context(MigrationContext.configure(sincrona)):
            modulo.downgrade()

    await conexion.run_sync(correr)
