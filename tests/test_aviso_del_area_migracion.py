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
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.modules.notifications.application.area_notices import (
    AVISO_DE_LA_APERTURA,
    AVISO_DE_PLANEACION,
    LARGO_DEL_TITULO,
)
from app.shared.infrastructure.db.constraints import viola_la_restriccion

RAIZ = Path(__file__).resolve().parents[1]
REVISION = "0042_aviso_del_area"

TABLA = "notificaciones"

COLUMNAS = {
    "id": ("integer", False, "nextval('notificaciones_id_seq'::regclass)"),
    "usuario_id": ("integer", False, None),
    "tipo": ("character varying(60)", False, None),
    "entidad": ("character varying(60)", True, None),
    "entidad_id": ("integer", True, None),
    "mensaje": ("text", False, None),
    "leida": ("boolean", False, "false"),
    "enviada_por_correo": ("boolean", False, "false"),
    "fecha": ("timestamp with time zone", False, "now()"),
    "origen_evento_id": ("uuid", True, None),
    "correo_reservado_hasta": ("timestamp with time zone", True, None),
    "titulo": ("character varying(200)", True, None),
}

LOS_SIETE_VALORES_DEL_ENUM = [
    "apertura_periodo",
    "validacion",
    "rechazo",
    "recordatorio_5d",
    "recordatorio_3d",
    "recordatorio_2d",
    "recordatorio_1d",
]


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


async def _intentar_insertar(conexion: AsyncConnection, tabla: str, **valores) -> DBAPIError:
    with pytest.raises(DBAPIError) as caido:
        async with conexion.begin_nested():
            await _insertar(conexion, tabla, **valores)
    return caido.value


async def _usuario(conexion: AsyncConnection) -> int:
    return await _insertar(
        conexion,
        "usuarios",
        nombre="Persona del area",
        correo=f"persona-{uuid4().hex}@upchiapas.edu.mx",
        hash_password="$argon2id$de$prueba",
        activo=True,
    )


async def _aviso(conexion: AsyncConnection, **valores) -> int:
    return await _insertar(
        conexion,
        TABLA,
        **{
            "usuario_id": await _usuario(conexion),
            "tipo": AVISO_DE_LA_APERTURA,
            "mensaje": "La Direccion de Planeacion habilito el registro de actividades.",
            **valores,
        },
    )


async def _sin_ningun_titulo_cargado(conexion: AsyncConnection) -> None:
    await conexion.execute(text(f"UPDATE {TABLA} SET titulo = NULL WHERE titulo IS NOT NULL"))


async def _esquema(conexion: AsyncConnection) -> dict[str, tuple]:
    filas = (
        await conexion.execute(
            text(
                "SELECT a.attname, format_type(a.atttypid, a.atttypmod), "
                "NOT a.attnotnull, pg_get_expr(d.adbin, d.adrelid) "
                "FROM pg_attribute a "
                "JOIN pg_class c ON c.oid = a.attrelid "
                "LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum "
                "WHERE c.relnamespace = 'public'::regnamespace AND c.relname = :tabla "
                "AND a.attnum > 0 AND NOT a.attisdropped"
            ),
            {"tabla": TABLA},
        )
    ).all()
    return {
        columna: (tipo, admite_nulo, por_omision)
        for columna, tipo, admite_nulo, por_omision in filas
    }


def _la_0042():
    return (
        ScriptDirectory.from_config(Config(str(RAIZ / "alembic.ini"))).get_revision(REVISION).module
    )


async def _correr(conexion: AsyncConnection, paso: str) -> None:
    modulo = _la_0042()

    def dentro(sincrona) -> None:
        with Operations.context(MigrationContext.configure(sincrona)):
            getattr(modulo, paso)()

    await conexion.run_sync(dentro)


async def test_las_notificaciones_declaran_estas_columnas_y_ninguna_mas(conexion):
    assert await _esquema(conexion) == COLUMNAS


async def test_el_titulo_admite_nulo_porque_los_avisos_anteriores_no_lo_tienen(conexion):
    aviso = await _aviso(conexion)

    guardado = (
        await conexion.execute(text(f"SELECT titulo FROM {TABLA} WHERE id = :id"), {"id": aviso})
    ).scalar_one()
    assert guardado is None


async def test_un_titulo_de_doscientos_caracteres_entra_y_uno_de_doscientos_uno_no(conexion):
    usuario = await _usuario(conexion)

    await _aviso(conexion, usuario_id=usuario, titulo="t" * LARGO_DEL_TITULO)

    error = await _intentar_insertar(
        conexion,
        TABLA,
        usuario_id=usuario,
        tipo=AVISO_DE_LA_APERTURA,
        mensaje="Un mensaje cualquiera.",
        titulo="t" * (LARGO_DEL_TITULO + 1),
    )
    assert "character varying(200)" in str(error.orig)


async def test_el_enum_de_siete_valores_sigue_con_sus_siete_valores(conexion):
    valores = (
        (
            await conexion.execute(
                text(
                    "SELECT enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
                    "WHERE t.typname = 'tipo_notificacion' ORDER BY e.enumsortorder"
                )
            )
        )
        .scalars()
        .all()
    )

    assert list(valores) == LOS_SIETE_VALORES_DEL_ENUM


async def test_ninguna_columna_de_la_base_usa_todavia_el_enum_de_notificaciones(conexion):
    columnas = (
        await conexion.execute(
            text(
                "SELECT c.relname, a.attname FROM pg_attribute a "
                "JOIN pg_class c ON c.oid = a.attrelid "
                "JOIN pg_type t ON t.oid = a.atttypid "
                "WHERE t.typname = 'tipo_notificacion' AND a.attnum > 0 "
                "AND NOT a.attisdropped"
            )
        )
    ).all()

    assert columnas == []


@pytest.mark.parametrize("tipo", [AVISO_DE_LA_APERTURA, AVISO_DE_PLANEACION])
async def test_los_dos_tipos_nuevos_entran_sin_ampliar_el_enum(conexion, tipo):
    aviso = await _aviso(conexion, tipo=tipo, titulo="Habilitacion del periodo de captura")

    guardado = (
        await conexion.execute(text(f"SELECT tipo FROM {TABLA} WHERE id = :id"), {"id": aviso})
    ).scalar_one()
    assert guardado == tipo


@pytest.mark.parametrize("tipo", [AVISO_DE_LA_APERTURA, AVISO_DE_PLANEACION])
async def test_los_tipos_nuevos_no_chocan_con_la_unicidad_de_los_recordatorios(conexion, tipo):
    usuario = await _usuario(conexion)
    comunes = dict(usuario_id=usuario, tipo=tipo, entidad="poa_inst_area", entidad_id=7)

    await _aviso(conexion, **comunes)
    await _aviso(conexion, **comunes)

    cuantos = (
        await conexion.execute(
            text(f"SELECT count(*) FROM {TABLA} WHERE usuario_id = :id"), {"id": usuario}
        )
    ).scalar_one()
    assert cuantos == 2


async def test_un_recordatorio_repetido_si_choca_con_su_unicidad(conexion):
    usuario = await _usuario(conexion)
    comunes = dict(usuario_id=usuario, tipo="recordatorio_5d", entidad="periodo", entidad_id=7)
    await _aviso(conexion, **comunes)

    error = await _intentar_insertar(conexion, TABLA, mensaje="El periodo vence pronto.", **comunes)

    assert viola_la_restriccion(error, "uq_notificaciones_recordatorio_unico")


async def test_el_mismo_aviso_del_mismo_evento_no_se_repite_para_la_misma_persona(conexion):
    usuario = await _usuario(conexion)
    evento = str(uuid4())
    comunes = dict(usuario_id=usuario, tipo=AVISO_DE_LA_APERTURA, origen_evento_id=evento)
    await _aviso(conexion, **comunes)

    error = await _intentar_insertar(conexion, TABLA, mensaje="El mismo aviso otra vez.", **comunes)

    assert viola_la_restriccion(error, "uq_notificaciones_evento_idempotente")


async def test_la_0042_no_se_baja_con_un_titulo_cargado(conexion):
    await _sin_ningun_titulo_cargado(conexion)
    await _aviso(conexion, titulo="Habilitacion del periodo de captura")

    with pytest.raises(RuntimeError, match=r"notificaciones\.titulo \(1\)"):
        await _correr(conexion, "downgrade")

    assert "titulo" in await _esquema(conexion)


async def test_la_0042_se_baja_y_se_sube_otra_vez_dejando_el_mismo_esquema(conexion):
    await _sin_ningun_titulo_cargado(conexion)
    columnas = await _esquema(conexion)

    await _correr(conexion, "downgrade")
    assert "titulo" not in await _esquema(conexion)

    await _correr(conexion, "upgrade")

    assert await _esquema(conexion) == columnas == COLUMNAS


async def test_una_notificacion_sin_mensaje_no_entra_aunque_traiga_titulo(conexion):
    error = await _intentar_insertar(
        conexion,
        TABLA,
        usuario_id=await _usuario(conexion),
        tipo=AVISO_DE_PLANEACION,
        titulo="Un aviso sin cuerpo",
    )

    assert isinstance(error, IntegrityError)
    assert getattr(getattr(error.orig, "__cause__", None), "column_name", None) == "mensaje"
