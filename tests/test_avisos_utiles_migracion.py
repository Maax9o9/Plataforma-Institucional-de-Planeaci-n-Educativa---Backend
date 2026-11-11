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
    AVISO_DE_PLANEACION,
    LARGO_DEL_DESTINO,
    LARGO_DEL_NOMBRE_DEL_ADJUNTO,
    LARGO_DEL_TITULO,
)
from app.shared.infrastructure.db.constraints import viola_la_restriccion

RAIZ = Path(__file__).resolve().parents[1]
REVISION = "0043_avisos_utiles"

COLUMNAS_DE_LOS_AVISOS = {
    "id": ("integer", False, "nextval('avisos_id_seq'::regclass)"),
    "titulo": (f"character varying({LARGO_DEL_TITULO})", False, None),
    "mensaje": ("text", False, None),
    "destino_ruta": (f"character varying({LARGO_DEL_DESTINO})", True, None),
    "vigente_hasta": ("date", True, None),
    "creado_por": ("integer", False, None),
    "creado_en": ("timestamp with time zone", False, "now()"),
}

COLUMNAS_DE_LOS_ADJUNTOS = {
    "id": ("integer", False, "nextval('aviso_adjuntos_id_seq'::regclass)"),
    "aviso_id": ("integer", False, None),
    "nombre": (f"character varying({LARGO_DEL_NOMBRE_DEL_ADJUNTO})", False, None),
    "ruta_o_url": ("character varying(500)", False, None),
    "mime_type": ("character varying(100)", False, None),
    "tamanio_bytes": ("bigint", False, None),
}

UN_DOCUMENTO = "a" * 32 + ".docx"
SU_TIPO = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


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
        nombre="Persona de la Direccion de Planeacion",
        correo=f"persona-{uuid4().hex}@upchiapas.edu.mx",
        hash_password="$argon2id$de$prueba",
        activo=True,
    )


async def _aviso(conexion: AsyncConnection, **valores) -> int:
    return await _insertar(
        conexion,
        "avisos",
        **{
            "titulo": "Entrega del Programa Operativo Anual",
            "mensaje": "Las areas entregan su Programa Operativo Anual.",
            "creado_por": await _usuario(conexion),
            **valores,
        },
    )


async def _adjunto(conexion: AsyncConnection, aviso_id: int, **valores) -> int:
    return await _insertar(
        conexion,
        "aviso_adjuntos",
        **{
            "aviso_id": aviso_id,
            "nombre": "Formato del Programa Operativo Anual.docx",
            "ruta_o_url": UN_DOCUMENTO,
            "mime_type": SU_TIPO,
            "tamanio_bytes": 24_576,
            **valores,
        },
    )


async def _notificacion(conexion: AsyncConnection, **valores) -> int:
    return await _insertar(
        conexion,
        "notificaciones",
        **{
            "usuario_id": await _usuario(conexion),
            "tipo": AVISO_DE_PLANEACION,
            "mensaje": "Las areas entregan su Programa Operativo Anual.",
            **valores,
        },
    )


async def _esquema(conexion: AsyncConnection, tabla: str) -> dict[str, tuple]:
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
            {"tabla": tabla},
        )
    ).all()
    return {
        columna: (tipo, admite_nulo, por_omision)
        for columna, tipo, admite_nulo, por_omision in filas
    }


async def _sin_ningun_aviso_cargado(conexion: AsyncConnection) -> None:
    await conexion.execute(text("UPDATE notificaciones SET aviso_id = NULL"))
    await conexion.execute(text("DELETE FROM aviso_adjuntos"))
    await conexion.execute(text("DELETE FROM avisos"))


def _la_0043():
    return (
        ScriptDirectory.from_config(Config(str(RAIZ / "alembic.ini"))).get_revision(REVISION).module
    )


async def _correr(conexion: AsyncConnection, paso: str) -> None:
    modulo = _la_0043()

    def dentro(sincrona) -> None:
        with Operations.context(MigrationContext.configure(sincrona)):
            getattr(modulo, paso)()

    await conexion.run_sync(dentro)


# ── El comunicado es un registro propio ──────────────────────────────────────


async def test_los_avisos_declaran_estas_columnas_y_ninguna_mas(conexion):
    assert await _esquema(conexion, "avisos") == COLUMNAS_DE_LOS_AVISOS


async def test_los_adjuntos_declaran_estas_columnas_y_ninguna_mas(conexion):
    assert await _esquema(conexion, "aviso_adjuntos") == COLUMNAS_DE_LOS_ADJUNTOS


async def test_un_aviso_se_guarda_sin_destino_y_sin_vigencia(conexion):
    aviso = await _aviso(conexion)

    guardado = (
        await conexion.execute(
            text("SELECT destino_ruta, vigente_hasta FROM avisos WHERE id = :id"), {"id": aviso}
        )
    ).one()
    assert (guardado.destino_ruta, guardado.vigente_hasta) == (None, None)


async def test_un_aviso_sin_quien_lo_redacto_no_entra(conexion):
    error = await _intentar_insertar(
        conexion,
        "avisos",
        titulo="Un aviso sin autor",
        mensaje="El cuerpo del aviso.",
    )

    assert isinstance(error, IntegrityError)
    assert getattr(getattr(error.orig, "__cause__", None), "column_name", None) == "creado_por"


async def test_un_aviso_de_una_cuenta_que_no_existe_no_entra(conexion):
    error = await _intentar_insertar(
        conexion,
        "avisos",
        titulo="Un aviso de nadie",
        mensaje="El cuerpo del aviso.",
        creado_por=10**8,
    )

    assert viola_la_restriccion(error, "fk_aviso_creado_por")


@pytest.mark.parametrize("en_blanco", ["", "   "])
async def test_un_aviso_con_el_titulo_en_blanco_no_entra(conexion, en_blanco):
    error = await _intentar_insertar(
        conexion,
        "avisos",
        titulo=en_blanco,
        mensaje="El cuerpo del aviso.",
        creado_por=await _usuario(conexion),
    )

    assert viola_la_restriccion(error, "chk_aviso_titulo_con_texto")


@pytest.mark.parametrize("en_blanco", ["", "   "])
async def test_un_aviso_con_el_mensaje_en_blanco_no_entra(conexion, en_blanco):
    error = await _intentar_insertar(
        conexion,
        "avisos",
        titulo="Un aviso sin cuerpo",
        mensaje=en_blanco,
        creado_por=await _usuario(conexion),
    )

    assert viola_la_restriccion(error, "chk_aviso_mensaje_con_texto")


@pytest.mark.parametrize(
    "destino",
    [
        "https://otro-sitio.example.com/formato",
        "//otro-sitio.example.com/formato",
        "javascript:alert(1)",
        "avisos",
    ],
)
async def test_el_destino_del_aviso_es_una_pantalla_del_sistema_y_no_un_sitio_de_fuera(
    conexion, destino
):
    error = await _intentar_insertar(
        conexion,
        "avisos",
        titulo="Un aviso con destino de fuera",
        mensaje="El cuerpo del aviso.",
        creado_por=await _usuario(conexion),
        destino_ruta=destino,
    )

    assert viola_la_restriccion(error, "chk_aviso_destino_del_sistema")


async def test_el_destino_del_aviso_admite_una_ruta_del_sistema(conexion):
    aviso = await _aviso(conexion, destino_ruta="/poa-institucional/mi-area")

    guardado = (
        await conexion.execute(
            text("SELECT destino_ruta FROM avisos WHERE id = :id"), {"id": aviso}
        )
    ).scalar_one()
    assert guardado == "/poa-institucional/mi-area"


# ── Los adjuntos del comunicado ──────────────────────────────────────────────


async def test_un_aviso_admite_varios_adjuntos(conexion):
    aviso = await _aviso(conexion)

    await _adjunto(conexion, aviso, ruta_o_url="a" * 32 + ".docx")
    await _adjunto(conexion, aviso, ruta_o_url="b" * 32 + ".pdf", mime_type="application/pdf")

    cuantos = (
        await conexion.execute(
            text("SELECT count(*) FROM aviso_adjuntos WHERE aviso_id = :id"), {"id": aviso}
        )
    ).scalar_one()
    assert cuantos == 2


async def test_el_mismo_archivo_no_se_adjunta_dos_veces_al_mismo_aviso(conexion):
    aviso = await _aviso(conexion)
    await _adjunto(conexion, aviso)

    error = await _intentar_insertar(
        conexion,
        "aviso_adjuntos",
        aviso_id=aviso,
        nombre="El mismo formato otra vez.docx",
        ruta_o_url=UN_DOCUMENTO,
        mime_type=SU_TIPO,
        tamanio_bytes=24_576,
    )

    assert viola_la_restriccion(error, "uq_aviso_adjunto_ruta")


async def test_el_mismo_archivo_se_adjunta_a_dos_avisos_distintos(conexion):
    uno = await _aviso(conexion)
    otro = await _aviso(conexion)

    await _adjunto(conexion, uno)
    await _adjunto(conexion, otro)

    cuantos = (
        await conexion.execute(
            text("SELECT count(*) FROM aviso_adjuntos WHERE ruta_o_url = :ruta"),
            {"ruta": UN_DOCUMENTO},
        )
    ).scalar_one()
    assert cuantos == 2


async def test_un_adjunto_de_un_aviso_que_no_existe_no_entra(conexion):
    error = await _intentar_insertar(
        conexion,
        "aviso_adjuntos",
        aviso_id=10**8,
        nombre="Formato del Programa Operativo Anual.docx",
        ruta_o_url=UN_DOCUMENTO,
        mime_type=SU_TIPO,
        tamanio_bytes=24_576,
    )

    assert viola_la_restriccion(error, "fk_aviso_adjunto_aviso")


async def test_un_adjunto_de_cero_bytes_no_entra(conexion):
    aviso = await _aviso(conexion)

    error = await _intentar_insertar(
        conexion,
        "aviso_adjuntos",
        aviso_id=aviso,
        nombre="Un archivo vacio.pdf",
        ruta_o_url="c" * 32 + ".pdf",
        mime_type="application/pdf",
        tamanio_bytes=0,
    )

    assert viola_la_restriccion(error, "chk_aviso_adjunto_tamanio")


async def test_borrar_un_aviso_se_lleva_sus_adjuntos_y_no_los_deja_huerfanos(conexion):
    aviso = await _aviso(conexion)
    await _adjunto(conexion, aviso)

    await conexion.execute(text("DELETE FROM avisos WHERE id = :id"), {"id": aviso})

    cuantos = (
        await conexion.execute(
            text("SELECT count(*) FROM aviso_adjuntos WHERE aviso_id = :id"), {"id": aviso}
        )
    ).scalar_one()
    assert cuantos == 0


# ── La notificacion es la entrega del comunicado ─────────────────────────────


async def test_la_notificacion_apunta_al_aviso_del_que_nacio(conexion):
    aviso = await _aviso(conexion)

    entrega = await _notificacion(conexion, aviso_id=aviso)

    guardado = (
        await conexion.execute(
            text("SELECT aviso_id FROM notificaciones WHERE id = :id"), {"id": entrega}
        )
    ).scalar_one()
    assert guardado == aviso


async def test_una_notificacion_que_no_nace_de_un_comunicado_apunta_a_nulo(conexion):
    entrega = await _notificacion(conexion, tipo="recordatorio_5d", entidad="periodo", entidad_id=7)

    guardado = (
        await conexion.execute(
            text("SELECT aviso_id FROM notificaciones WHERE id = :id"), {"id": entrega}
        )
    ).scalar_one()
    assert guardado is None


async def test_las_entregas_del_mismo_aviso_se_agrupan_por_su_aviso(conexion):
    aviso = await _aviso(conexion)
    otro = await _aviso(conexion)
    await _notificacion(conexion, aviso_id=aviso)
    await _notificacion(conexion, aviso_id=aviso, leida=True)
    await _notificacion(conexion, aviso_id=otro)

    contadas = (
        await conexion.execute(
            text(
                "SELECT count(*) AS entregados, count(*) FILTER (WHERE leida) AS leidos "
                "FROM notificaciones WHERE aviso_id = :id"
            ),
            {"id": aviso},
        )
    ).one()
    assert (contadas.entregados, contadas.leidos) == (2, 1)


async def test_una_entrega_de_un_aviso_que_no_existe_no_entra(conexion):
    error = await _intentar_insertar(
        conexion,
        "notificaciones",
        usuario_id=await _usuario(conexion),
        tipo=AVISO_DE_PLANEACION,
        mensaje="El cuerpo del aviso.",
        aviso_id=10**8,
    )

    assert viola_la_restriccion(error, "fk_notificacion_aviso")


async def test_un_aviso_con_entregas_no_se_borra_y_se_lleva_el_rastro_de_quien_lo_leyo(conexion):
    aviso = await _aviso(conexion)
    await _notificacion(conexion, aviso_id=aviso)

    with pytest.raises(DBAPIError) as caido:
        async with conexion.begin_nested():
            await conexion.execute(text("DELETE FROM avisos WHERE id = :id"), {"id": aviso})

    assert viola_la_restriccion(caido.value, "fk_notificacion_aviso")


async def test_el_origen_del_evento_sigue_impidiendo_la_entrega_repetida(conexion):
    aviso = await _aviso(conexion)
    usuario = await _usuario(conexion)
    evento = str(uuid4())
    comunes = dict(
        usuario_id=usuario, tipo=AVISO_DE_PLANEACION, origen_evento_id=evento, aviso_id=aviso
    )
    await _notificacion(conexion, **comunes)

    error = await _intentar_insertar(
        conexion, "notificaciones", mensaje="El mismo aviso otra vez.", **comunes
    )

    assert viola_la_restriccion(error, "uq_notificaciones_evento_idempotente")


# ── Subir y bajar ────────────────────────────────────────────────────────────


async def test_la_0043_no_se_baja_con_un_aviso_cargado(conexion):
    await _sin_ningun_aviso_cargado(conexion)
    await _aviso(conexion)

    with pytest.raises(RuntimeError, match=r"avisos \(1\)"):
        await _correr(conexion, "downgrade")

    assert "aviso_id" in await _esquema(conexion, "notificaciones")


async def test_la_0043_no_se_baja_con_una_entrega_que_apunta_a_un_aviso(conexion):
    await _sin_ningun_aviso_cargado(conexion)
    aviso = await _aviso(conexion)
    await _notificacion(conexion, aviso_id=aviso)
    await conexion.execute(text("DELETE FROM avisos WHERE false"))

    with pytest.raises(RuntimeError, match=r"notificaciones\.aviso_id \(1\)"):
        await _correr(conexion, "downgrade")

    assert "aviso_id" in await _esquema(conexion, "notificaciones")


async def test_la_0043_se_baja_y_se_sube_otra_vez_dejando_el_mismo_esquema(conexion):
    await _sin_ningun_aviso_cargado(conexion)
    avisos = await _esquema(conexion, "avisos")
    adjuntos = await _esquema(conexion, "aviso_adjuntos")
    notificaciones = await _esquema(conexion, "notificaciones")

    await _correr(conexion, "downgrade")
    assert await _esquema(conexion, "avisos") == {}
    assert await _esquema(conexion, "aviso_adjuntos") == {}
    assert "aviso_id" not in await _esquema(conexion, "notificaciones")

    await _correr(conexion, "upgrade")

    assert await _esquema(conexion, "avisos") == avisos == COLUMNAS_DE_LOS_AVISOS
    assert await _esquema(conexion, "aviso_adjuntos") == adjuntos == COLUMNAS_DE_LOS_ADJUNTOS
    assert await _esquema(conexion, "notificaciones") == notificaciones
