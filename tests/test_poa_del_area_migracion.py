from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
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

from app.shared.infrastructure.db.constraints import viola_la_restriccion

pytestmark = pytest.mark.asyncio

RAIZ = Path(__file__).resolve().parents[1]
REVISION = "0040_poa_inst_del_area"

TABLAS = ("poa_inst_areas", "poa_inst_actividades", "poa_inst_programacion_mensual")

COLUMNAS = {
    "poa_inst_areas": {
        "id": ("integer", False, "nextval('poa_inst_areas_id_seq'::regclass)"),
        "ejercicio_id": ("integer", False, None),
        "area_id": ("integer", False, None),
        "estado": ("character varying(30)", False, "'borrador'::character varying"),
        "creado_en": ("timestamp with time zone", False, "now()"),
    },
    "poa_inst_actividades": {
        "id": ("integer", False, "nextval('poa_inst_actividades_id_seq'::regclass)"),
        "poa_area_id": ("integer", False, None),
        "nodo_id": ("integer", True, None),
        "denominacion": ("text", False, None),
        "unidad_medida_id": ("integer", True, None),
        "metodo_evaluacion": ("text", True, None),
        "meta_anual": ("numeric(18,4)", True, None),
        "version": ("integer", False, "1"),
        "activo": ("boolean", False, "true"),
    },
    "poa_inst_programacion_mensual": {
        "id": ("integer", False, "nextval('poa_inst_programacion_mensual_id_seq'::regclass)"),
        "actividad_id": ("integer", False, None),
        "mes": ("smallint", False, None),
        "meta": ("numeric(18,4)", False, None),
        "programado": ("boolean", False, None),
    },
}

LLAVES_FORANEAS = {
    "fk_poa_inst_area_ejercicio": (
        "FOREIGN KEY (ejercicio_id) REFERENCES poa_ejercicios(id) ON DELETE RESTRICT"
    ),
    "fk_poa_inst_area_area": "FOREIGN KEY (area_id) REFERENCES areas(id) ON DELETE RESTRICT",
    "fk_poa_inst_actividad_poa_area": (
        "FOREIGN KEY (poa_area_id) REFERENCES poa_inst_areas(id) ON DELETE RESTRICT"
    ),
    "fk_poa_inst_actividad_nodo": (
        "FOREIGN KEY (nodo_id) REFERENCES nodos_estrategicos(id) ON DELETE RESTRICT"
    ),
    "fk_poa_inst_actividad_unidad_medida": (
        "FOREIGN KEY (unidad_medida_id) REFERENCES unidades_medida(id) ON DELETE RESTRICT"
    ),
    "fk_poa_inst_programacion_actividad": (
        "FOREIGN KEY (actividad_id) REFERENCES poa_inst_actividades(id) ON DELETE RESTRICT"
    ),
}

RESTRICCIONES = {
    "poa_inst_areas_pkey": "p",
    "fk_poa_inst_area_ejercicio": "f",
    "fk_poa_inst_area_area": "f",
    "uq_poa_inst_area_ejercicio_area": "u",
    "chk_poa_inst_area_estado": "c",
    "poa_inst_actividades_pkey": "p",
    "fk_poa_inst_actividad_poa_area": "f",
    "fk_poa_inst_actividad_nodo": "f",
    "fk_poa_inst_actividad_unidad_medida": "f",
    "chk_poa_inst_actividad_meta_anual_no_negativa": "c",
    "poa_inst_programacion_mensual_pkey": "p",
    "fk_poa_inst_programacion_actividad": "f",
    "uq_poa_inst_programacion_actividad_mes": "u",
    "chk_poa_inst_programacion_mes": "c",
    "chk_poa_inst_programacion_meta_no_negativa": "c",
}

PADRE_DE = {
    "fk_poa_inst_area_ejercicio": ("poa_ejercicios", "ejercicio"),
    "fk_poa_inst_area_area": ("areas", "area"),
    "fk_poa_inst_actividad_poa_area": ("poa_inst_areas", "poa_area"),
    "fk_poa_inst_actividad_nodo": ("nodos_estrategicos", "nodo"),
    "fk_poa_inst_actividad_unidad_medida": ("unidades_medida", "unidad"),
    "fk_poa_inst_programacion_actividad": ("poa_inst_actividades", "actividad"),
}

LO_QUE_CUELGA_DE_LAS_TABLAS_DE_LA_0040 = {
    "poa_inst_areas": (
        "CREATE TABLE sonda_cuelga_del_poa_del_area (id serial PRIMARY KEY, poa_area_id integer, "
        "CONSTRAINT fk_sonda_poa_area FOREIGN KEY (poa_area_id) REFERENCES poa_inst_areas(id))"
    ),
    "poa_inst_actividades": (
        "CREATE TABLE sonda_cuelga_de_la_actividad (id serial PRIMARY KEY, actividad_id integer, "
        "CONSTRAINT fk_sonda_actividad FOREIGN KEY (actividad_id) "
        "REFERENCES poa_inst_actividades(id))"
    ),
    "poa_inst_programacion_mensual": (
        "CREATE TABLE sonda_cuelga_del_mes (id serial PRIMARY KEY, mes_id integer, "
        "CONSTRAINT fk_sonda_mes FOREIGN KEY (mes_id) "
        "REFERENCES poa_inst_programacion_mensual(id))"
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


async def _ejercicio(conexion: AsyncConnection) -> int:
    anio = (
        await conexion.execute(
            text(
                "SELECT min(anio) FROM generate_series(2000, 2200) AS anio "
                "WHERE anio NOT IN (SELECT anio FROM poa_ejercicios)"
            )
        )
    ).scalar_one()
    catalogo = await _insertar(
        conexion, "poa_catalogos", nombre=f"POA de prueba {uuid4().hex}", anio=anio
    )
    return await _insertar(conexion, "poa_ejercicios", anio=anio, catalogo_id=catalogo)


async def _area(conexion: AsyncConnection) -> int:
    return await _insertar(conexion, "areas", nombre=f"Area de prueba {uuid4().hex}")


async def _unidad(conexion: AsyncConnection) -> int:
    return await _insertar(
        conexion,
        "unidades_medida",
        clave=f"prueba-{uuid4().hex[:20]}",
        nombre="Unidad de prueba",
        plural="Unidades de prueba",
    )


async def _nodo(conexion: AsyncConnection) -> int:
    instrumento = await _insertar(
        conexion, "instrumentos", nombre=f"Instrumento de prueba {uuid4().hex[:20]}"
    )
    version = await _insertar(
        conexion,
        "instrumento_versiones",
        instrumento_id=instrumento,
        etiqueta="V1",
        vigente_desde=date(2025, 1, 1),
    )
    return await _insertar(
        conexion,
        "nodos_estrategicos",
        version_id=version,
        tipo="accion",
        clave="1.1.1.1.1",
        denominacion="Accion de prueba",
        orden=1,
    )


async def _poa_area(
    conexion: AsyncConnection, ejercicio: int | None = None, area: int | None = None, **valores
) -> int:
    return await _insertar(
        conexion,
        "poa_inst_areas",
        ejercicio_id=ejercicio if ejercicio is not None else await _ejercicio(conexion),
        area_id=area if area is not None else await _area(conexion),
        **valores,
    )


async def _actividad(conexion: AsyncConnection, poa_area: int | None = None, **valores) -> int:
    return await _insertar(
        conexion,
        "poa_inst_actividades",
        poa_area_id=poa_area if poa_area is not None else await _poa_area(conexion),
        **{"denominacion": "Actividad de prueba", **valores},
    )


async def _programar(
    conexion: AsyncConnection, actividad: int, mes: int, meta: Decimal, programado: bool
) -> int:
    return await _insertar(
        conexion,
        "poa_inst_programacion_mensual",
        actividad_id=actividad,
        mes=mes,
        meta=meta,
        programado=programado,
    )


@pytest.fixture
async def cadena(conexion):
    ejercicio = await _ejercicio(conexion)
    area = await _area(conexion)
    unidad = await _unidad(conexion)
    nodo = await _nodo(conexion)
    poa_area = await _poa_area(conexion, ejercicio, area)
    actividad = await _actividad(
        conexion, poa_area, nodo_id=nodo, unidad_medida_id=unidad, meta_anual=Decimal(10)
    )
    await _programar(conexion, actividad, 1, Decimal(10), True)
    await _programar(conexion, actividad, 2, Decimal(0), False)
    return {
        "ejercicio": ejercicio,
        "area": area,
        "unidad": unidad,
        "nodo": nodo,
        "poa_area": poa_area,
        "actividad": actividad,
    }


async def _existe(conexion: AsyncConnection, tabla: str) -> bool:
    return (
        await conexion.execute(text("SELECT to_regclass(:tabla)"), {"tabla": tabla})
    ).scalar_one() is not None


async def _esquema(conexion: AsyncConnection) -> dict[str, dict[str, tuple]]:
    listado = ", ".join(f"'{tabla}'" for tabla in TABLAS)
    filas = (
        await conexion.execute(
            text(
                "SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod), "
                "NOT a.attnotnull, pg_get_expr(d.adbin, d.adrelid) "
                "FROM pg_attribute a "
                "JOIN pg_class c ON c.oid = a.attrelid "
                "LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum "
                f"WHERE c.relnamespace = 'public'::regnamespace AND c.relname IN ({listado}) "
                "AND a.attnum > 0 AND NOT a.attisdropped"
            )
        )
    ).all()
    esquema: dict[str, dict[str, tuple]] = {}
    for tabla, columna, tipo, admite_nulo, por_omision in filas:
        esquema.setdefault(tabla, {})[columna] = (tipo, admite_nulo, por_omision)
    return esquema


async def _restricciones(conexion: AsyncConnection) -> dict[str, tuple[str, str]]:
    listado = ", ".join(f"'{tabla}'" for tabla in TABLAS)
    filas = (
        await conexion.execute(
            text(
                "SELECT k.conname, k.contype::text, pg_get_constraintdef(k.oid) "
                "FROM pg_constraint k JOIN pg_class c ON c.oid = k.conrelid "
                f"WHERE c.relnamespace = 'public'::regnamespace AND c.relname IN ({listado}) "
                "AND k.contype IN ('p', 'f', 'u', 'c')"
            )
        )
    ).all()
    return {nombre: (tipo, definicion) for nombre, tipo, definicion in filas}


def _la_0040():
    return (
        ScriptDirectory.from_config(Config(str(RAIZ / "alembic.ini"))).get_revision(REVISION).module
    )


async def _bajar_la_0040(conexion: AsyncConnection) -> None:
    modulo = _la_0040()

    def correr(sincrona) -> None:
        with Operations.context(MigrationContext.configure(sincrona)):
            modulo.downgrade()

    await conexion.run_sync(correr)


async def _subir_la_0040(conexion: AsyncConnection) -> None:
    modulo = _la_0040()

    def correr(sincrona) -> None:
        with Operations.context(MigrationContext.configure(sincrona)):
            modulo.upgrade()

    await conexion.run_sync(correr)


async def test_el_esquema_de_las_tres_tablas_es_el_que_las_tareas_siguientes_dan_por_cierto(
    conexion,
):
    assert await _esquema(conexion) == COLUMNAS


async def test_un_mes_no_programado_se_distingue_de_un_cero(conexion):
    actividad = await _actividad(conexion)
    esperado = {2: False, 3: True, 8: True, 11: False}
    for mes, programado in esperado.items():
        await _programar(conexion, actividad, mes, Decimal(0), programado)

    guardado = (
        await conexion.execute(
            text(
                "SELECT mes, meta, programado FROM poa_inst_programacion_mensual "
                "WHERE actividad_id = :actividad ORDER BY mes"
            ),
            {"actividad": actividad},
        )
    ).all()

    assert [mes for mes, _, _ in guardado] == [2, 3, 8, 11]
    assert all(meta == 0 for _, meta, _ in guardado)
    assert all(programado is esperado[mes] for mes, _, programado in guardado)


@pytest.mark.parametrize("omitido", ["programado", "meta"])
async def test_cada_mes_declara_cuanto_y_si_se_programa_sin_valores_por_omision(conexion, omitido):
    actividad = await _actividad(conexion)
    valores = {"actividad_id": actividad, "mes": 5, "meta": Decimal(0), "programado": True}
    del valores[omitido]

    error = await _intentar_insertar(conexion, "poa_inst_programacion_mensual", **valores)

    assert _columna_sin_valor(error) == omitido


async def test_un_area_tiene_un_solo_poa_por_ejercicio(conexion):
    ejercicio = await _ejercicio(conexion)
    area = await _area(conexion)
    await _poa_area(conexion, ejercicio, area, estado="borrador")

    error = await _intentar_insertar(
        conexion, "poa_inst_areas", ejercicio_id=ejercicio, area_id=area, estado="enviado"
    )

    assert viola_la_restriccion(error, "uq_poa_inst_area_ejercicio_area")


async def test_otra_area_u_otro_ejercicio_tienen_su_propio_poa(conexion):
    ejercicio = await _ejercicio(conexion)
    otro_ejercicio = await _ejercicio(conexion)
    area = await _area(conexion)
    otra_area = await _area(conexion)

    await _poa_area(conexion, ejercicio, area)
    await _poa_area(conexion, otro_ejercicio, area)
    await _poa_area(conexion, ejercicio, otra_area)
    await _poa_area(conexion, otro_ejercicio, otra_area)

    cuantos = (
        await conexion.execute(
            text("SELECT count(*) FROM poa_inst_areas WHERE ejercicio_id IN (:uno, :otro)"),
            {"uno": ejercicio, "otro": otro_ejercicio},
        )
    ).scalar_one()
    assert cuantos == 4


@pytest.mark.parametrize("estado", ["borrador", "enviado"])
async def test_el_estado_de_un_poa_de_area_es_uno_de_los_dos_del_primer_tramo(conexion, estado):
    poa_area = await _poa_area(conexion, estado=estado)

    guardado = (
        await conexion.execute(
            text("SELECT estado FROM poa_inst_areas WHERE id = :id"), {"id": poa_area}
        )
    ).scalar_one()
    assert guardado == estado


@pytest.mark.parametrize(
    "estado", ["", "Borrador", "ENVIADO", "borrador ", "presentado", "aprobado", "cerrado"]
)
async def test_un_estado_que_el_primer_tramo_no_usa_no_entra(conexion, estado):
    error = await _intentar_insertar(
        conexion,
        "poa_inst_areas",
        ejercicio_id=await _ejercicio(conexion),
        area_id=await _area(conexion),
        estado=estado,
    )

    assert viola_la_restriccion(error, "chk_poa_inst_area_estado")


@pytest.mark.parametrize("mes", range(1, 13))
async def test_cada_uno_de_los_doce_meses_se_programa(conexion, mes):
    actividad = await _actividad(conexion)

    await _programar(conexion, actividad, mes, Decimal(1), True)


@pytest.mark.parametrize("mes", [-1, 0, 13, 99])
async def test_un_mes_fuera_de_1_a_12_no_entra(conexion, mes):
    actividad = await _actividad(conexion)

    error = await _intentar_insertar(
        conexion,
        "poa_inst_programacion_mensual",
        actividad_id=actividad,
        mes=mes,
        meta=Decimal(1),
        programado=True,
    )

    assert viola_la_restriccion(error, "chk_poa_inst_programacion_mes")


async def test_un_mes_no_se_programa_dos_veces_en_la_misma_actividad(conexion):
    actividad = await _actividad(conexion)
    await _programar(conexion, actividad, 4, Decimal(0), False)

    error = await _intentar_insertar(
        conexion,
        "poa_inst_programacion_mensual",
        actividad_id=actividad,
        mes=4,
        meta=Decimal(5),
        programado=True,
    )

    assert viola_la_restriccion(error, "uq_poa_inst_programacion_actividad_mes")


async def test_otra_actividad_u_otro_mes_se_programan_aparte(conexion):
    actividad = await _actividad(conexion)
    otra_actividad = await _actividad(conexion)

    await _programar(conexion, actividad, 4, Decimal(1), True)
    await _programar(conexion, actividad, 5, Decimal(1), True)
    await _programar(conexion, otra_actividad, 4, Decimal(1), True)
    await _programar(conexion, otra_actividad, 5, Decimal(1), True)

    cuantos = (
        await conexion.execute(
            text(
                "SELECT count(*) FROM poa_inst_programacion_mensual "
                "WHERE actividad_id IN (:una, :otra)"
            ),
            {"una": actividad, "otra": otra_actividad},
        )
    ).scalar_one()
    assert cuantos == 4


@pytest.mark.parametrize("meta", [Decimal("-0.0001"), Decimal("-1")])
async def test_una_meta_anual_negativa_no_entra_pero_cero_si(conexion, meta):
    poa_area = await _poa_area(conexion)
    await _actividad(conexion, poa_area, meta_anual=Decimal(0))

    error = await _intentar_insertar(
        conexion,
        "poa_inst_actividades",
        poa_area_id=poa_area,
        denominacion="Con meta negativa",
        meta_anual=meta,
    )

    assert viola_la_restriccion(error, "chk_poa_inst_actividad_meta_anual_no_negativa")


@pytest.mark.parametrize("meta", [Decimal("-0.0001"), Decimal("-1")])
async def test_una_meta_mensual_negativa_no_entra_pero_cero_si(conexion, meta):
    actividad = await _actividad(conexion)
    await _programar(conexion, actividad, 1, Decimal(0), True)

    error = await _intentar_insertar(
        conexion,
        "poa_inst_programacion_mensual",
        actividad_id=actividad,
        mes=2,
        meta=meta,
        programado=True,
    )

    assert viola_la_restriccion(error, "chk_poa_inst_programacion_meta_no_negativa")


async def test_un_borrador_incompleto_se_guarda_con_solo_su_nombre(conexion):
    poa_area = await _poa_area(conexion)
    actividad = await _insertar(
        conexion, "poa_inst_actividades", poa_area_id=poa_area, denominacion="Apenas empezada"
    )

    fila = (
        await conexion.execute(
            text(
                "SELECT nodo_id, unidad_medida_id, metodo_evaluacion, meta_anual, version, activo "
                "FROM poa_inst_actividades WHERE id = :id"
            ),
            {"id": actividad},
        )
    ).one()

    assert (fila.nodo_id, fila.unidad_medida_id, fila.metodo_evaluacion, fila.meta_anual) == (
        None,
        None,
        None,
        None,
    )
    assert fila.version == 1
    assert fila.activo is True


async def test_un_poa_de_area_admite_varias_actividades_del_mismo_nodo_y_la_misma_unidad(conexion):
    poa_area = await _poa_area(conexion)
    nodo = await _nodo(conexion)
    unidad = await _unidad(conexion)

    primera = await _actividad(
        conexion, poa_area, denominacion="Primera", nodo_id=nodo, unidad_medida_id=unidad
    )
    segunda = await _actividad(
        conexion, poa_area, denominacion="Segunda", nodo_id=nodo, unidad_medida_id=unidad
    )

    assert primera != segunda


async def test_las_tablas_declaran_estas_restricciones_y_ninguna_mas(conexion):
    restricciones = await _restricciones(conexion)

    assert {nombre: tipo for nombre, (tipo, _) in restricciones.items()} == RESTRICCIONES


async def test_las_llaves_foraneas_son_las_seis_y_todas_son_restrict(conexion):
    foraneas = {
        nombre: definicion
        for nombre, (tipo, definicion) in (await _restricciones(conexion)).items()
        if tipo == "f"
    }

    assert foraneas == LLAVES_FORANEAS


@pytest.mark.parametrize("restriccion", list(PADRE_DE))
async def test_lo_que_ya_se_usa_no_se_borra(conexion, cadena, restriccion):
    tabla, clave = PADRE_DE[restriccion]

    error = await _intentar_borrar(conexion, tabla, cadena[clave])

    assert viola_la_restriccion(error, restriccion)


async def test_la_0040_no_se_baja_con_un_poa_de_area_cargado(conexion):
    await _poa_area(conexion)

    with pytest.raises(RuntimeError, match=r"poa_inst_areas \(1\)"):
        await _bajar_la_0040(conexion)

    assert [await _existe(conexion, tabla) for tabla in TABLAS] == [True, True, True]


async def test_la_0040_se_niega_nombrando_cada_tabla_con_su_conteo(conexion, cadena):
    with pytest.raises(RuntimeError) as caido:
        await _bajar_la_0040(conexion)

    mensaje = str(caido.value)
    assert "poa_inst_areas (1)" in mensaje
    assert "poa_inst_actividades (1)" in mensaje
    assert "poa_inst_programacion_mensual (2)" in mensaje
    assert [await _existe(conexion, tabla) for tabla in TABLAS] == [True, True, True]


async def test_la_0040_se_baja_cuando_las_tablas_estan_vacias(conexion):
    await _bajar_la_0040(conexion)

    assert [await _existe(conexion, tabla) for tabla in TABLAS] == [False, False, False]


@pytest.mark.parametrize("cuelga_de", list(LO_QUE_CUELGA_DE_LAS_TABLAS_DE_LA_0040))
async def test_la_0040_no_se_baja_llevandose_lo_que_cuelga_de_sus_tablas(conexion, cuelga_de):
    await conexion.execute(text(LO_QUE_CUELGA_DE_LAS_TABLAS_DE_LA_0040[cuelga_de]))
    intento = await conexion.begin_nested()

    with pytest.raises(DBAPIError, match=f"cannot drop table {cuelga_de}"):
        await _bajar_la_0040(conexion)

    await intento.rollback()
    sondas = (
        await conexion.execute(
            text("SELECT count(*) FROM pg_constraint WHERE conname LIKE 'fk_sonda%'")
        )
    ).scalar_one()
    assert sondas == 1
    assert [await _existe(conexion, tabla) for tabla in TABLAS] == [True, True, True]


async def test_la_0040_se_sube_otra_vez_tras_bajarla_y_deja_el_mismo_esquema(conexion):
    columnas = await _esquema(conexion)
    restricciones = await _restricciones(conexion)
    await _bajar_la_0040(conexion)
    assert await _esquema(conexion) == {}
    assert await _restricciones(conexion) == {}

    await _subir_la_0040(conexion)

    assert await _esquema(conexion) == columnas == COLUMNAS
    assert await _restricciones(conexion) == restricciones
