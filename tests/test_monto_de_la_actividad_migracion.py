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

from app.shared.infrastructure.db.constraints import viola_la_restriccion

RAIZ = Path(__file__).resolve().parents[1]
REVISION = "0044_monto_de_la_actividad"


@pytest.fixture
def url() -> str:
    valor = os.getenv("TEST_DATABASE_URL")
    if not valor:
        pytest.skip("TEST_DATABASE_URL no configurada")
    return valor


@pytest.fixture
async def conexion(url):
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


async def _insertar(conexion: AsyncConnection, tabla: str, **valores) -> int:
    columnas = ", ".join(valores)
    marcadores = ", ".join(f":{columna}" for columna in valores)
    return (
        await conexion.execute(
            text(f"INSERT INTO {tabla} ({columnas}) VALUES ({marcadores}) RETURNING id"),
            valores,
        )
    ).scalar_one()


async def _un_poa_del_area(conexion: AsyncConnection) -> int:
    anio = await _un_anio_libre(conexion)
    catalogo = await _insertar(
        conexion,
        "poa_catalogos",
        nombre=f"POA de prueba {uuid4().hex[:8]}",
        anio=anio,
    )
    ejercicio = await _insertar(
        conexion,
        "poa_ejercicios",
        anio=anio,
        catalogo_id=catalogo,
    )
    area = await _insertar(
        conexion,
        "areas",
        nombre=f"Área de prueba {uuid4().hex[:8]}",
    )
    return await _insertar(
        conexion,
        "poa_inst_areas",
        ejercicio_id=ejercicio,
        area_id=area,
    )


async def _un_anio_libre(conexion: AsyncConnection) -> int:
    mayor = (
        await conexion.execute(text("SELECT COALESCE(MAX(anio), 1999) FROM poa_ejercicios"))
    ).scalar_one()
    return int(mayor) + 1


async def _actividad(conexion: AsyncConnection, **valores) -> int:
    return await _insertar(
        conexion,
        "poa_inst_actividades",
        **{
            "poa_area_id": await _un_poa_del_area(conexion),
            "denominacion": "Equipar el laboratorio de biomecánica",
            **valores,
        },
    )


async def _esquema(conexion: AsyncConnection, tabla: str, columna: str) -> tuple:
    return (
        await conexion.execute(
            text(
                "SELECT format_type(a.atttypid, a.atttypmod), NOT a.attnotnull "
                "FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid "
                "WHERE c.relnamespace = 'public'::regnamespace AND c.relname = :tabla "
                "AND a.attname = :columna AND NOT a.attisdropped"
            ),
            {"tabla": tabla, "columna": columna},
        )
    ).one()


async def _correr(conexion: AsyncConnection, paso: str) -> None:
    modulo = (
        ScriptDirectory.from_config(Config(str(RAIZ / "alembic.ini"))).get_revision(REVISION).module
    )

    def dentro(sincrona) -> None:
        with Operations.context(MigrationContext.configure(sincrona)):
            getattr(modulo, paso)()

    await conexion.run_sync(dentro)


async def test_el_monto_se_guarda_con_centavos_y_admite_nulo(conexion):
    assert await _esquema(conexion, "poa_inst_actividades", "monto_solicitado") == (
        "numeric(16,2)",
        True,
    )


async def test_una_actividad_sin_monto_sigue_entrando(conexion):
    actividad = await _actividad(conexion)

    guardado = (
        await conexion.execute(
            text("SELECT monto_solicitado FROM poa_inst_actividades WHERE id = :id"),
            {"id": actividad},
        )
    ).scalar_one()
    assert guardado is None


async def test_el_monto_capturado_conserva_sus_centavos(conexion):
    actividad = await _actividad(conexion, monto_solicitado="1250.55")

    guardado = (
        await conexion.execute(
            text("SELECT monto_solicitado FROM poa_inst_actividades WHERE id = :id"),
            {"id": actividad},
        )
    ).scalar_one()
    assert str(guardado) == "1250.55"


async def test_un_monto_negativo_no_entra(conexion):
    with pytest.raises(DBAPIError) as caido:
        async with conexion.begin_nested():
            await _actividad(conexion, monto_solicitado="-1")

    assert viola_la_restriccion(caido.value, "ck_poa_inst_actividad_monto_no_negativo")


async def test_bajar_la_migracion_con_montos_capturados_se_rechaza(conexion):
    await _actividad(conexion, monto_solicitado="1000")

    with pytest.raises(RuntimeError):
        async with conexion.begin_nested():
            await _correr(conexion, "downgrade")
