"""La migracion que parte el catalogo por POA, sin perder lo que ya existe.

Solo corre contra PostgreSQL: la migracion es SQL crudo y el repositorio en
memoria no la ejecuta.

Las tres pruebas se siembran a si mismas y revierten al salir. No pueden
apoyarse en lo que inserto la migracion porque `tests/conftest.py` vacia las
tablas de la aplicacion al arrancar la sesion: el renglon "POA 2026" ya no
esta cuando esto corre. Asi que lo que se comprueba aqui es el contrato de
esquema, que si es repetible, y el comportamiento sobre datos propios.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import TextClause, bindparam, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

# Las ocho tablas que la migracion ata a un POA.
TABLAS_CON_CATALOGO = (
    "poa_catalogo_objetivos",
    "poa_catalogo_estrategias",
    "poa_catalogo_indicadores",
    "poa_catalogo_actividades",
    "poa_ejercicios",
    "poa_cedulas",
    "poa_cedula_indicadores",
    "poa_cedula_actividades",
)

# Las cuatro del catalogo, cuya clave deja de valer en todo el sistema para
# valer dentro de su POA.
TABLAS_DEL_CATALOGO = TABLAS_CON_CATALOGO[:4]


def _en(sql: str) -> TextClause:
    """Consulta con `IN :tablas` expandido a un parametro por tabla."""
    return text(sql).bindparams(bindparam("tablas", expanding=True))


@pytest.fixture
def url() -> str:
    valor = os.getenv("TEST_DATABASE_URL")
    if not valor:
        pytest.skip("TEST_DATABASE_URL no configurada")
    return valor


@pytest.fixture
async def conexion(url):
    """Conexion cuya transaccion se revierte siempre.

    Las pruebas siembran POA, ejercicios y cedulas de verdad. Revertir al
    salir las deja autosuficientes y repetibles sin ensuciar la base, que
    persiste entre corridas.
    """
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


async def _catalogo(conexion: AsyncConnection, nombre: str, anio: int, claves: tuple[str, ...]):
    """Siembra un POA con su objetivo 1 y las estrategias que se le pidan."""
    catalogo = (
        await conexion.execute(
            text(
                "INSERT INTO poa_catalogos (nombre, anio, origen) "
                "VALUES (:nombre, :anio, 'prueba') RETURNING id"
            ),
            {"nombre": nombre, "anio": anio},
        )
    ).scalar_one()
    await conexion.execute(
        text(
            "INSERT INTO poa_catalogo_objetivos (catalogo_id, numero, clave, denominacion) "
            "VALUES (:catalogo, 1, 'OBJ-1', 'Objetivo de prueba')"
        ),
        {"catalogo": catalogo},
    )
    for clave in claves:
        await conexion.execute(
            text(
                "INSERT INTO poa_catalogo_estrategias "
                "(catalogo_id, clave, objetivo_numero, denominacion) "
                "VALUES (:catalogo, :clave, 1, :denominacion)"
            ),
            {
                "catalogo": catalogo,
                "clave": clave,
                "denominacion": f"Estrategia {clave} del catalogo {nombre}",
            },
        )
    return catalogo


async def _ejercicio(conexion: AsyncConnection, anio: int, catalogo: int) -> int:
    return (
        await conexion.execute(
            text(
                "INSERT INTO poa_ejercicios (anio, catalogo_id) "
                "VALUES (:anio, :catalogo) RETURNING id"
            ),
            {"anio": anio, "catalogo": catalogo},
        )
    ).scalar_one()


@pytest.mark.asyncio
async def test_el_esquema_cuelga_el_catalogo_de_su_poa(conexion):
    """Tras migrar, el catalogo entero cuelga de un POA y ninguna de sus
    llaves vale ya en todo el sistema. Es el contrato que las nueve tareas
    siguientes dan por cierto, y lo unico de la migracion que es repetible:
    los datos que sembro los vacia `conftest` antes de que esto corra."""
    tablas = {"tablas": list(TABLAS_CON_CATALOGO)}

    existe = (
        await conexion.execute(
            text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = 'poa_catalogos'"
            )
        )
    ).scalar_one()
    assert existe == 1

    # Nadie puede quedar sin POA: la columna es obligatoria en las ocho.
    columnas = dict(
        (
            await conexion.execute(
                _en(
                    "SELECT table_name, is_nullable FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND column_name = 'catalogo_id' "
                    "AND table_name IN :tablas"
                ),
                tablas,
            )
        ).all()
    )
    assert columnas == dict.fromkeys(TABLAS_CON_CATALOGO, "NO")

    # Las cuatro llaves primarias del catalogo arrancan con el POA.
    primeras = dict(
        (
            await conexion.execute(
                _en(
                    "SELECT t.relname, a.attname FROM pg_index i "
                    "JOIN pg_class t ON t.oid = i.indrelid "
                    "JOIN pg_attribute a "
                    "  ON a.attrelid = i.indrelid AND a.attnum = i.indkey[0] "
                    "WHERE i.indisprimary AND t.relname IN :tablas"
                ),
                {"tablas": list(TABLAS_DEL_CATALOGO)},
            )
        ).all()
    )
    assert primeras == dict.fromkeys(TABLAS_DEL_CATALOGO, "catalogo_id")

    # Y ninguna unica del catalogo se quedo sin el POA: mientras quede una,
    # dos POA no pueden repetir esa clave y copiar un POA entero es imposible.
    globales = (
        await conexion.execute(
            _en(
                "SELECT t.relname, i.indexrelid::regclass::text "
                "FROM pg_index i JOIN pg_class t ON t.oid = i.indrelid "
                "WHERE i.indisunique AND t.relname IN :tablas "
                "AND strpos(pg_get_indexdef(i.indexrelid), 'catalogo_id') = 0"
            ),
            {"tablas": list(TABLAS_DEL_CATALOGO)},
        )
    ).all()
    assert globales == []

    # Ni quedo una foranea apuntando a una llave del catalogo sin el POA: por
    # ahi se colaria una cedula al catalogo de otro ano.
    foraneas = (
        await conexion.execute(
            text(
                "SELECT c.conrelid::regclass::text, c.conname "
                "FROM pg_constraint c "
                "WHERE c.contype = 'f' "
                "AND starts_with(c.confrelid::regclass::text, 'poa_catalogo_') "
                "AND strpos(pg_get_constraintdef(c.oid), 'catalogo_id') = 0"
            )
        )
    ).all()
    assert foraneas == []

    # Y las foraneas que van de un renglon de cedula a su cedula borran todas
    # en cascada, igual que la que ya existia por `cedula_id`. Si una cascada y
    # la otra no, borrar una cedula depende de cual revise Postgres primero
    # -el orden de los disparadores RI, que va por nombre con el OID dentro- y
    # al restaurar un respaldo ese orden se invierte.
    desacuerdos = (
        await conexion.execute(
            _en(
                "SELECT c.conrelid::regclass::text, c.conname, c.confdeltype "
                "FROM pg_constraint c "
                "WHERE c.contype = 'f' AND c.confrelid = 'poa_cedulas'::regclass "
                "AND c.conrelid::regclass::text IN :tablas "
                "AND c.confdeltype <> 'c'"
            ),
            {"tablas": ["poa_cedula_indicadores", "poa_cedula_actividades"]},
        )
    ).all()
    assert desacuerdos == []


@pytest.mark.asyncio
async def test_dos_poa_pueden_tener_la_misma_clave(conexion):
    """Es lo que hoy es imposible: la clave deja de ser unica en todo el
    sistema para serlo dentro de su POA. Vale para el objetivo y para la
    estrategia: los dos POA repiten 'OBJ-1' y '1.1' con otro texto."""
    sufijo = uuid4().hex[:8]
    uno = await _catalogo(conexion, f"POA de prueba 2098 {sufijo}", 2098, ("1.1",))
    otro = await _catalogo(conexion, f"POA de prueba 2099 {sufijo}", 2099, ("1.1",))

    cuantas = (
        await conexion.execute(
            text(
                "SELECT count(*) FROM poa_catalogo_estrategias "
                "WHERE clave = '1.1' AND catalogo_id IN (:uno, :otro)"
            ),
            {"uno": uno, "otro": otro},
        )
    ).scalar_one()
    assert cuantas == 2

    denominaciones = (
        await conexion.execute(
            text(
                "SELECT denominacion FROM poa_catalogo_estrategias "
                "WHERE clave = '1.1' AND catalogo_id IN (:uno, :otro)"
            ),
            {"uno": uno, "otro": otro},
        )
    ).scalars()
    assert len(set(denominaciones)) == 2


@pytest.mark.asyncio
async def test_una_cedula_no_puede_apuntar_al_catalogo_de_otro_poa(conexion):
    """Lo impide la base, no el codigo: si dependiera del caso de uso, un
    endpoint nuevo podria saltarselo sin que nadie lo notara."""
    sufijo = uuid4().hex[:8]
    propio = await _catalogo(conexion, f"POA propio {sufijo}", 2097, ("1.1", "1.2"))
    # El de al lado repite la clave '1.1' -ya puede- pero no tiene la '1.2'.
    ajeno = await _catalogo(conexion, f"POA ajeno {sufijo}", 2096, ("1.1",))

    area = (
        await conexion.execute(
            text("INSERT INTO areas (nombre) VALUES (:nombre) RETURNING id"),
            {"nombre": f"Area de prueba {sufijo}"},
        )
    ).scalar_one()
    usuario = (
        await conexion.execute(
            text(
                "INSERT INTO usuarios (nombre, correo, hash_password) "
                "VALUES ('Prueba 0037', :correo, 'test-only-hash') RETURNING id"
            ),
            {"correo": f"migracion-0037-{sufijo}@example.com"},
        )
    ).scalar_one()

    # El anio del ejercicio es unico y la base persiste entre corridas.
    base = (
        await conexion.execute(text("SELECT coalesce(max(anio), 2000) FROM poa_ejercicios"))
    ).scalar_one()
    ejercicio_propio = await _ejercicio(conexion, base + 1, propio)
    ejercicio_ajeno = await _ejercicio(conexion, base + 2, ajeno)

    cedula = (
        await conexion.execute(
            text(
                "INSERT INTO poa_cedulas (ejercicio_id, objetivo_numero, estrategia_clave, "
                "area_responsable_id, creado_por, catalogo_id) "
                "VALUES (:ejercicio, 1, '1.1', :area, :usuario, :catalogo) RETURNING id"
            ),
            {
                "ejercicio": ejercicio_propio,
                "area": area,
                "usuario": usuario,
                "catalogo": propio,
            },
        )
    ).scalar_one()

    # Cambiarle el catalogo dejandole el ejercicio: la cedula y su ejercicio
    # tienen que mirar al mismo POA.
    with pytest.raises(IntegrityError) as desalineada:
        async with conexion.begin_nested():
            await conexion.execute(
                text("UPDATE poa_cedulas SET catalogo_id = :ajeno WHERE id = :cedula"),
                {"ajeno": ajeno, "cedula": cedula},
            )
    assert "fk_poa_cedula_ejercicio_catalogo" in str(desalineada.value)

    # Mudarla entera al POA de al lado tampoco: la estrategia '1.2' es del
    # catalogo que deja atras, y alla no existe.
    with pytest.raises(IntegrityError) as prestada:
        async with conexion.begin_nested():
            await conexion.execute(
                text(
                    "UPDATE poa_cedulas SET ejercicio_id = :ejercicio, catalogo_id = :ajeno, "
                    "estrategia_clave = '1.2' WHERE id = :cedula"
                ),
                {"ejercicio": ejercicio_ajeno, "ajeno": ajeno, "cedula": cedula},
            )
    assert "fk_poa_cedula_estrategia" in str(prestada.value)

    # Y su numero de objetivo sigue teniendo que ser el del objetivo de su
    # estrategia: la '1.1' es del objetivo 1, asi que decir 2 revienta. Esto es
    # lo que la foranea garantiza por llevar tres columnas y no dos; con dos
    # -(catalogo_id, estrategia_clave)- este UPDATE pasaria sin ruido y la
    # cedula quedaria diciendo que su estrategia cuelga de otro objetivo.
    with pytest.raises(IntegrityError) as descolgada:
        async with conexion.begin_nested():
            await conexion.execute(
                text("UPDATE poa_cedulas SET objetivo_numero = 2 WHERE id = :cedula"),
                {"cedula": cedula},
            )
    assert "fk_poa_cedula_estrategia" in str(descolgada.value)
