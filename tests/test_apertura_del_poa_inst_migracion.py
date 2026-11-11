from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.shared.infrastructure.db.constraints import viola_la_restriccion
from helpers import (
    PRIMER_ANIO_DEL_CONTRATO,
    SE_ACABARON_LOS_ANIOS,
    ULTIMO_ANIO_DEL_CONTRATO,
)

RAIZ = Path(__file__).resolve().parents[1]
REVISION = "0041_apertura_del_poa_inst"

TABLA = "poa_inst_aperturas"

COLUMNAS = {
    "id": ("integer", False, "nextval('poa_inst_aperturas_id_seq'::regclass)"),
    "poa_area_id": ("integer", False, None),
    "numero": ("integer", False, None),
    "desde": ("date", False, None),
    "hasta": ("date", False, None),
    "motivo": ("text", True, None),
    "abierto_por": ("integer", True, None),
    "creado_en": ("timestamp with time zone", False, "now()"),
}

RESTRICCIONES = {
    "poa_inst_aperturas_pkey": "p",
    "fk_poa_inst_apertura_poa_area": "f",
    "fk_poa_inst_apertura_abierto_por": "f",
    "uq_poa_inst_apertura_poa_area_numero": "u",
    "chk_poa_inst_apertura_numero": "c",
    "chk_poa_inst_apertura_fechas": "c",
    "chk_poa_inst_apertura_motivo_de_la_reapertura": "c",
}

LLAVES_FORANEAS = {
    "fk_poa_inst_apertura_poa_area": (
        "FOREIGN KEY (poa_area_id) REFERENCES poa_inst_areas(id) ON DELETE RESTRICT"
    ),
    "fk_poa_inst_apertura_abierto_por": (
        "FOREIGN KEY (abierto_por) REFERENCES usuarios(id) ON DELETE RESTRICT"
    ),
}


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


async def _intentar_insertar(conexion: AsyncConnection, tabla: str, **valores) -> IntegrityError:
    with pytest.raises(IntegrityError) as caido:
        async with conexion.begin_nested():
            await _insertar(conexion, tabla, **valores)
    return caido.value


async def _intentar_borrar(conexion: AsyncConnection, tabla: str, identificador: int):
    with pytest.raises(IntegrityError) as caido:
        async with conexion.begin_nested():
            await conexion.execute(
                text(f"DELETE FROM {tabla} WHERE id = :id"), {"id": identificador}
            )
    return caido.value


def _columna_sin_valor(error: IntegrityError) -> str | None:
    causa = getattr(error.orig, "__cause__", None)
    return getattr(causa, "column_name", None)


async def _anio_libre(conexion: AsyncConnection, desde: int = PRIMER_ANIO_DEL_CONTRATO) -> int:
    libre = (
        await conexion.execute(
            text(
                f"SELECT min(anio) FROM generate_series(:desde, {ULTIMO_ANIO_DEL_CONTRATO}) "
                "AS anio WHERE anio NOT IN (SELECT anio FROM poa_ejercicios)"
            ),
            {"desde": desde},
        )
    ).scalar_one()
    if libre is None:
        pytest.fail(
            f"{SE_ACABARON_LOS_ANIOS}: no queda ninguno libre entre {desde} y "
            f"{ULTIMO_ANIO_DEL_CONTRATO}. Estas pruebas revierten su transacción, así que "
            "el pozo lo gastó otro archivo."
        )
    return libre


async def _ejercicio(conexion: AsyncConnection, anio: int | None = None) -> tuple[int, int]:
    elegido = anio if anio is not None else await _anio_libre(conexion)
    catalogo = await _insertar(
        conexion, "poa_catalogos", nombre=f"POA de prueba {uuid4().hex}", anio=elegido
    )
    ejercicio = await _insertar(conexion, "poa_ejercicios", anio=elegido, catalogo_id=catalogo)
    return ejercicio, elegido


async def _area(conexion: AsyncConnection) -> int:
    return await _insertar(conexion, "areas", nombre=f"Area de prueba {uuid4().hex}")


async def _usuario(conexion: AsyncConnection) -> int:
    return await _insertar(
        conexion,
        "usuarios",
        nombre="Persona de Planeacion",
        correo=f"persona-{uuid4().hex}@upchiapas.edu.mx",
        hash_password="$argon2id$de$prueba",
        activo=True,
    )


async def _poa_area(conexion: AsyncConnection, **valores) -> int:
    ejercicio, _ = await _ejercicio(conexion)
    return await _insertar(
        conexion,
        "poa_inst_areas",
        ejercicio_id=ejercicio,
        area_id=await _area(conexion),
        **valores,
    )


async def _apertura(conexion: AsyncConnection, poa_area: int, **valores) -> int:
    return await _insertar(
        conexion,
        TABLA,
        poa_area_id=poa_area,
        **{"numero": 1, "desde": date(2026, 1, 1), "hasta": date(2026, 12, 31), **valores},
    )


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


async def _restricciones(conexion: AsyncConnection) -> dict[str, tuple[str, str]]:
    filas = (
        await conexion.execute(
            text(
                "SELECT k.conname, k.contype::text, pg_get_constraintdef(k.oid) "
                "FROM pg_constraint k JOIN pg_class c ON c.oid = k.conrelid "
                "WHERE c.relnamespace = 'public'::regnamespace AND c.relname = :tabla "
                "AND k.contype IN ('p', 'f', 'u', 'c')"
            ),
            {"tabla": TABLA},
        )
    ).all()
    return {nombre: (tipo, definicion) for nombre, tipo, definicion in filas}


async def _existe(conexion: AsyncConnection, tabla: str) -> bool:
    return (
        await conexion.execute(text("SELECT to_regclass(:tabla)"), {"tabla": tabla})
    ).scalar_one() is not None


def _la_0041():
    return (
        ScriptDirectory.from_config(Config(str(RAIZ / "alembic.ini"))).get_revision(REVISION).module
    )


async def _correr(conexion: AsyncConnection, paso: str) -> None:
    modulo = _la_0041()

    def dentro(sincrona) -> None:
        with Operations.context(MigrationContext.configure(sincrona)):
            getattr(modulo, paso)()

    await conexion.run_sync(dentro)


async def test_la_tabla_de_aperturas_declara_estas_columnas_y_ninguna_mas(conexion):
    assert await _esquema(conexion) == COLUMNAS


async def test_la_tabla_de_aperturas_declara_estas_restricciones_y_ninguna_mas(conexion):
    restricciones = await _restricciones(conexion)

    assert {nombre: tipo for nombre, (tipo, _) in restricciones.items()} == RESTRICCIONES


async def test_las_dos_llaves_foraneas_de_la_apertura_son_restrict(conexion):
    foraneas = {
        nombre: definicion
        for nombre, (tipo, definicion) in (await _restricciones(conexion)).items()
        if tipo == "f"
    }

    assert foraneas == LLAVES_FORANEAS


async def test_la_apertura_se_indexa_por_el_poa_del_area(conexion):
    indices = (
        (
            await conexion.execute(
                text("SELECT indexname FROM pg_indexes WHERE tablename = :tabla"), {"tabla": TABLA}
            )
        )
        .scalars()
        .all()
    )

    assert "idx_poa_inst_aperturas_poa_area" in indices


@pytest.mark.parametrize("omitido", ["poa_area_id", "numero", "desde", "hasta"])
async def test_la_apertura_exige_el_poa_del_area_su_numero_y_las_dos_fechas(conexion, omitido):
    valores = {
        "poa_area_id": await _poa_area(conexion),
        "numero": 1,
        "desde": date(2026, 1, 1),
        "hasta": date(2026, 12, 31),
    }
    del valores[omitido]

    error = await _intentar_insertar(conexion, TABLA, **valores)

    assert _columna_sin_valor(error) == omitido


async def test_una_ventana_de_un_solo_dia_es_legal(conexion):
    poa_area = await _poa_area(conexion)

    await _apertura(conexion, poa_area, desde=date(2026, 11, 30), hasta=date(2026, 11, 30))


async def test_una_ventana_que_cierra_antes_de_abrir_no_entra(conexion):
    poa_area = await _poa_area(conexion)

    error = await _intentar_insertar(
        conexion,
        TABLA,
        poa_area_id=poa_area,
        numero=1,
        desde=date(2026, 11, 30),
        hasta=date(2026, 11, 29),
    )

    assert viola_la_restriccion(error, "chk_poa_inst_apertura_fechas")


@pytest.mark.parametrize("numero", [0, -1, -100])
async def test_un_numero_de_apertura_menor_que_uno_no_entra(conexion, numero):
    poa_area = await _poa_area(conexion)

    error = await _intentar_insertar(
        conexion,
        TABLA,
        poa_area_id=poa_area,
        numero=numero,
        desde=date(2026, 1, 1),
        hasta=date(2026, 12, 31),
        motivo="Un motivo cualquiera",
    )

    assert viola_la_restriccion(error, "chk_poa_inst_apertura_numero")


async def test_la_primera_apertura_no_necesita_motivo(conexion):
    poa_area = await _poa_area(conexion)

    apertura = await _apertura(conexion, poa_area, numero=1)

    guardado = (
        await conexion.execute(text(f"SELECT motivo FROM {TABLA} WHERE id = :id"), {"id": apertura})
    ).scalar_one()
    assert guardado is None


@pytest.mark.parametrize("numero", [2, 3, 17])
async def test_una_reapertura_sin_motivo_no_entra(conexion, numero):
    poa_area = await _poa_area(conexion)
    await _apertura(conexion, poa_area, numero=1)

    error = await _intentar_insertar(
        conexion,
        TABLA,
        poa_area_id=poa_area,
        numero=numero,
        desde=date(2027, 1, 1),
        hasta=date(2027, 3, 31),
    )

    assert viola_la_restriccion(error, "chk_poa_inst_apertura_motivo_de_la_reapertura")


@pytest.mark.parametrize("numero", [2, 3, 17])
async def test_una_reapertura_con_motivo_si_entra(conexion, numero):
    poa_area = await _poa_area(conexion)
    await _apertura(conexion, poa_area, numero=1)

    await _apertura(
        conexion,
        poa_area,
        numero=numero,
        desde=date(2027, 1, 1),
        hasta=date(2027, 3, 31),
        motivo="El area no entrego en la fecha dispuesta",
    )


async def test_un_poa_del_area_no_repite_el_numero_de_apertura(conexion):
    poa_area = await _poa_area(conexion)
    await _apertura(conexion, poa_area, numero=2, motivo="La primera reapertura")

    error = await _intentar_insertar(
        conexion,
        TABLA,
        poa_area_id=poa_area,
        numero=2,
        desde=date(2028, 1, 1),
        hasta=date(2028, 1, 31),
        motivo="Otra reapertura con el mismo numero",
    )

    assert viola_la_restriccion(error, "uq_poa_inst_apertura_poa_area_numero")


async def test_otro_poa_del_area_lleva_su_propia_cuenta_de_aperturas(conexion):
    uno = await _poa_area(conexion)
    otro = await _poa_area(conexion)

    await _apertura(conexion, uno, numero=1)
    await _apertura(conexion, otro, numero=1)

    cuantas = (
        await conexion.execute(
            text(f"SELECT count(*) FROM {TABLA} WHERE poa_area_id IN (:uno, :otro)"),
            {"uno": uno, "otro": otro},
        )
    ).scalar_one()
    assert cuantas == 2


async def test_la_apertura_admite_no_saber_quien_la_hizo(conexion):
    poa_area = await _poa_area(conexion)

    apertura = await _apertura(conexion, poa_area, abierto_por=None)

    guardado = (
        await conexion.execute(
            text(f"SELECT abierto_por FROM {TABLA} WHERE id = :id"), {"id": apertura}
        )
    ).scalar_one()
    assert guardado is None


async def test_la_apertura_guarda_quien_la_hizo_y_la_hora_en_que_se_hizo(conexion):
    poa_area = await _poa_area(conexion)
    usuario = await _usuario(conexion)

    apertura = await _apertura(conexion, poa_area, abierto_por=usuario)

    fila = (
        await conexion.execute(
            text(
                f"SELECT abierto_por, creado_en = now() AS con_la_hora FROM {TABLA} WHERE id = :id"
            ),
            {"id": apertura},
        )
    ).one()
    assert fila.abierto_por == usuario
    assert fila.con_la_hora is True


async def test_quien_abrio_tiene_que_existir(conexion):
    poa_area = await _poa_area(conexion)

    error = await _intentar_insertar(
        conexion,
        TABLA,
        poa_area_id=poa_area,
        numero=1,
        desde=date(2026, 1, 1),
        hasta=date(2026, 12, 31),
        abierto_por=10**9,
    )

    assert viola_la_restriccion(error, "fk_poa_inst_apertura_abierto_por")


async def test_la_apertura_cuelga_de_un_poa_del_area_que_existe(conexion):
    error = await _intentar_insertar(
        conexion,
        TABLA,
        poa_area_id=10**9,
        numero=1,
        desde=date(2026, 1, 1),
        hasta=date(2026, 12, 31),
    )

    assert viola_la_restriccion(error, "fk_poa_inst_apertura_poa_area")


async def test_un_poa_del_area_con_aperturas_no_se_borra(conexion):
    poa_area = await _poa_area(conexion)
    await _apertura(conexion, poa_area)

    error = await _intentar_borrar(conexion, "poa_inst_areas", poa_area)

    assert viola_la_restriccion(error, "fk_poa_inst_apertura_poa_area")


async def test_quien_abrio_un_poa_no_se_borra(conexion):
    poa_area = await _poa_area(conexion)
    usuario = await _usuario(conexion)
    await _apertura(conexion, poa_area, abierto_por=usuario)

    error = await _intentar_borrar(conexion, "usuarios", usuario)

    assert viola_la_restriccion(error, "fk_poa_inst_apertura_abierto_por")


async def _poa_area_con_fecha_de_creacion(
    conexion: AsyncConnection, anio: int, creado: date
) -> int:
    ejercicio, _ = await _ejercicio(conexion, anio)
    return await _insertar(
        conexion,
        "poa_inst_areas",
        ejercicio_id=ejercicio,
        area_id=await _area(conexion),
        creado_en=creado,
    )


async def _relleno_de(conexion: AsyncConnection, poa_area: int):
    return (
        await conexion.execute(
            text(
                f"SELECT numero, desde, hasta, motivo, abierto_por, creado_en::date AS creado "
                f"FROM {TABLA} WHERE poa_area_id = :id"
            ),
            {"id": poa_area},
        )
    ).all()


async def test_el_relleno_le_da_a_cada_poa_ya_abierto_su_apertura_numero_uno(conexion):
    await _correr(conexion, "downgrade")
    abierto_el = date(2026, 3, 4)
    # Un ano libre posterior a la fecha de apertura: el 31 de diciembre de ese
    # ano es la fecha de cierre derivable, y es la que la prueba comprueba.
    anio = await _anio_libre(conexion, 2100)
    poa_area = await _poa_area_con_fecha_de_creacion(conexion, anio, abierto_el)

    await _correr(conexion, "upgrade")

    assert await _relleno_de(conexion, poa_area) == [
        (1, abierto_el, date(anio, 12, 31), None, None, abierto_el)
    ]


async def test_el_relleno_no_borra_ningun_poa_ya_abierto(conexion):
    await _correr(conexion, "downgrade")
    cuantos = [await _poa_area(conexion) for _ in range(3)]

    await _correr(conexion, "upgrade")

    siguen = (
        await conexion.execute(
            text("SELECT count(*) FROM poa_inst_areas WHERE id = ANY(:ids)"), {"ids": cuantos}
        )
    ).scalar_one()
    rellenados = (
        await conexion.execute(
            text(f"SELECT count(*) FROM {TABLA} WHERE poa_area_id = ANY(:ids)"), {"ids": cuantos}
        )
    ).scalar_one()
    assert (siguen, rellenados) == (3, 3)


async def test_el_relleno_de_un_poa_abierto_despues_de_su_ano_no_cierra_antes_de_abrir(conexion):
    await _correr(conexion, "downgrade")
    abierto_el = date(2026, 11, 1)
    # Un ano libre que ya termino antes de la fecha de apertura: ahi el 31 de
    # diciembre quedaria antes de `desde` y `chk_poa_inst_apertura_fechas`
    # rechazaria la fila que no hay que perder.
    anio = await _anio_libre(conexion)
    assert date(anio, 12, 31) < abierto_el
    poa_area = await _poa_area_con_fecha_de_creacion(conexion, anio, abierto_el)

    await _correr(conexion, "upgrade")

    assert await _relleno_de(conexion, poa_area) == [
        (1, abierto_el, abierto_el, None, None, abierto_el)
    ]


async def test_la_0041_no_se_baja_con_una_apertura_cargada(conexion):
    await _apertura(conexion, await _poa_area(conexion))

    with pytest.raises(RuntimeError, match=r"poa_inst_aperturas \(1\)"):
        await _correr(conexion, "downgrade")

    assert await _existe(conexion, TABLA) is True


async def test_la_0041_se_baja_y_se_sube_otra_vez_dejando_el_mismo_esquema(conexion):
    columnas = await _esquema(conexion)
    restricciones = await _restricciones(conexion)

    await _correr(conexion, "downgrade")
    assert await _existe(conexion, TABLA) is False

    await _correr(conexion, "upgrade")

    assert await _esquema(conexion) == columnas == COLUMNAS
    assert await _restricciones(conexion) == restricciones


async def test_el_dia_de_hoy_cabe_en_una_ventana_que_lo_incluye_por_los_dos_bordes(conexion):
    poa_area = await _poa_area(conexion)
    hoy = date(2026, 11, 1)
    await _apertura(conexion, poa_area, desde=hoy, hasta=hoy + timedelta(days=1))

    dentro = (
        await conexion.execute(
            text(
                f"SELECT :hoy BETWEEN desde AND hasta AS dentro FROM {TABLA} "
                "WHERE poa_area_id = :id"
            ),
            {"hoy": hoy, "id": poa_area},
        )
    ).scalar_one()
    assert dentro is True
