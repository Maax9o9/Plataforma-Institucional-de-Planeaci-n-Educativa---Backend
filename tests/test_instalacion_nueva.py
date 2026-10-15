"""Una instalacion nueva nace con su catalogo sembrado.

Lo que cubre, y nada cubria, es el recorrido entero de un despliegue limpio:
migrar desde cero y arrancar la aplicacion por primera vez. El defecto que
descubre era de composicion y no vivia en ningun diff: la 0037 insertaba la
cabecera «POA 2026» sin condicion y `ensure_catalogs()` se da por sembrada en
cuanto encuentra un POA, asi que la aplicacion levantaba sin un solo error con
las cuatro tablas del catalogo vacias y la pantalla del catalogo en blanco. Las
pruebas no lo tocaban porque `tests/conftest.py` vacia `poa_catalogos` al
arrancar la sesion, asi que ahi el sembrado si corre.

La segunda prueba cubre la otra rama de la condicion -donde si hay catalogo
que adoptar-, que es el camino por el que la 0037 ya paso en las dos bases
locales y la razon por la que volverla condicional no divergio de lo aplicado.

Las dos corren sobre una base **propia y desechable**, que crean y tiran:
migrar desde cero exige una base que se pueda tirar, y ni `planeacion` -los
datos de verdad- ni la de `TEST_DATABASE_URL` -la que usa el resto de la
suite- lo son. Si no se puede crear, se saltan diciendo por que: una prueba
que revienta por el entorno es peor que una que se salta.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import asyncpg
import pytest

from app.core.config import Settings
from app.main import create_app

RAIZ = Path(__file__).resolve().parents[1]

#: La base que estas pruebas crean y tiran. Lleva otro nombre a proposito. El
#: nombre es fijo y no lleva sufijo al azar para que, si una corrida muere sin
#: limpiar, la siguiente barra la huerfana en vez de dejar una por corrida; se
#: puede porque la suite corre en serie y la fixture es de cada prueba.
BASE_DESECHABLE = "planeacion_recien_nacida"

#: Las que esta prueba no puede crear ni tirar jamas, pase lo que pase con el
#: nombre de arriba. `planeacion` tiene los datos reales y `planeacion_test` la
#: usa toda la suite; las tres de PostgreSQL ni se discuten.
BASES_INTOCABLES = frozenset(
    {"planeacion", "planeacion_test", "postgres", "template0", "template1"}
)

#: El catalogo que deja el primer arranque: es el formato institucional
#: completo de `app/modules/poa_planning/infrastructure/reference_data.py`,
#: colgando de un unico POA.
CATALOGO_DEL_PRIMER_ARRANQUE = {
    "poas": 1,
    "objetivos": 6,
    "estrategias": 24,
    "indicadores": 11,
    "acciones": 150,
}

#: Un catalogo minimo como el que una instalacion viva ya tenia antes de la
#: 0037: sin `catalogo_id`, que es justo la columna que la 0037 agrega. Uno de
#: cada tabla basta -lo que se mide es que la cabecera se ponga y los adopte-,
#: y la cadena completa objetivo -> estrategia -> accion la exigen las foraneas
#: de la 0022.
CATALOGO_DE_ANTES = (
    "INSERT INTO poa_catalogo_objetivos (numero, clave, denominacion) "
    "VALUES (1, 'OBJ-1', 'Objetivo que ya estaba')",
    "INSERT INTO poa_catalogo_estrategias (clave, objetivo_numero, denominacion) "
    "VALUES ('1.1', 1, 'Estrategia que ya estaba')",
    "INSERT INTO poa_catalogo_indicadores (clave, objetivo_numero, nombre, formula, unidad_medida) "
    "VALUES ('IND-1', 1, 'Indicador que ya estaba', '(a / b) * 100', 'Porcentaje')",
    "INSERT INTO poa_catalogo_actividades (clave, estrategia_clave, descripcion) "
    "VALUES ('1.1.1', '1.1', 'Accion que ya estaba')",
)

_CONTEOS = (
    "SELECT (SELECT count(*) FROM poa_catalogos)            AS poas,"
    "       (SELECT count(*) FROM poa_catalogo_objetivos)   AS objetivos,"
    "       (SELECT count(*) FROM poa_catalogo_estrategias) AS estrategias,"
    "       (SELECT count(*) FROM poa_catalogo_indicadores) AS indicadores,"
    "       (SELECT count(*) FROM poa_catalogo_actividades) AS acciones"
)

#: De cuantos POA distintos cuelga el catalogo. Que las cuatro tablas sumen lo
#: que se espera no basta: podrian estar repartidas entre dos cabeceras.
_DUENOS = (
    "SELECT DISTINCT catalogo_id FROM poa_catalogo_objetivos "
    "UNION SELECT catalogo_id FROM poa_catalogo_estrategias "
    "UNION SELECT catalogo_id FROM poa_catalogo_indicadores "
    "UNION SELECT catalogo_id FROM poa_catalogo_actividades "
    "ORDER BY 1"
)


def _base_de(url: str) -> str:
    """El nombre de la base que la URL apunta."""
    return urlsplit(url).path.lstrip("/")


def _con_base(url: str, base: str) -> str:
    """La misma URL apuntando a otra base: mismo servidor, mismas credenciales."""
    return urlunsplit(urlsplit(url)._replace(path=f"/{base}"))


def _dsn(url: str) -> str:
    """La URL como la entiende asyncpg, sin el dialecto de SQLAlchemy."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _comprobar_que_es_desechable(url_de_la_suite: str) -> None:
    """Para en seco si el nombre desechable es el de una base que no es suya.

    Se comprueba antes de ejecutar un solo DDL, porque esta prueba hace `CREATE
    DATABASE` y `DROP DATABASE`: un `DROP` sobre `planeacion` es el unico error
    de esta suite que no se puede deshacer, y un renombre descuidado de
    `BASE_DESECHABLE` -o una `TEST_DATABASE_URL` que apunte a los datos de
    verdad- es todo lo que haria falta. Falla, no se salta: que el nombre
    coincida con una base real no es una condicion del entorno, es un error.
    """
    if BASE_DESECHABLE in BASES_INTOCABLES:
        pytest.fail(f"«{BASE_DESECHABLE}» no es desechable: esta prueba la tiraria.")
    if BASE_DESECHABLE == _base_de(url_de_la_suite):
        pytest.fail(
            f"«{BASE_DESECHABLE}» es la base de TEST_DATABASE_URL, que usa el resto de la suite."
        )


async def _consultar(url: str, consulta: str):
    """Abre, pregunta y cierra. Cierra siempre porque la base se tira despues."""
    conexion = await asyncpg.connect(_dsn(url))
    try:
        return await conexion.fetch(consulta)
    finally:
        await conexion.close()


async def _sembrar(url: str, sentencias: tuple[str, ...]) -> None:
    """Ejecuta las sentencias en orden, en una sola conexion."""
    conexion = await asyncpg.connect(_dsn(url))
    try:
        for sentencia in sentencias:
            await conexion.execute(sentencia)
    finally:
        await conexion.close()


def _migrar(url: str, revision: str) -> None:
    """Corre Alembic contra la base desechable, en un proceso aparte.

    Aparte y no en el mismo porque `alembic/env.py` lee la URL de `Settings` y
    abre su propio bucle de asyncio: la variable de entorno gana sobre el
    `.env`, asi que esto apunta a la base desechable y no a la configurada.
    """
    corrida = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", revision],
        cwd=RAIZ,
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert corrida.returncode == 0, corrida.stderr


@pytest.fixture
async def base_recien_nacida():
    """Una base vacia, sin migrar, que se tira al salir pase lo que pase."""
    url_de_la_suite = os.getenv("TEST_DATABASE_URL")
    if not url_de_la_suite:
        pytest.skip("TEST_DATABASE_URL no configurada: no hay servidor donde crear la base")
    _comprobar_que_es_desechable(url_de_la_suite)

    # `CREATE DATABASE` no se puede ejecutar desde dentro de la base que se
    # crea, asi que la conexion va a la de mantenimiento del mismo servidor.
    mantenimiento = _dsn(_con_base(url_de_la_suite, "postgres"))
    try:
        conexion = await asyncpg.connect(mantenimiento)
    except (OSError, asyncpg.PostgresError) as fallo:
        pytest.skip(f"No se pudo conectar a «postgres» para crear la base desechable: {fallo}")

    # `FORCE` desaloja lo que haya quedado conectado (PostgreSQL 13 y arriba;
    # el proyecto corre 16). El `DROP` de antes barre la huerfana que pudiera
    # haber dejado una corrida muerta: `CREATE` sobre una base que ya existe
    # fallaria, y la prueba exige nacer vacia.
    tirar = f'DROP DATABASE IF EXISTS "{BASE_DESECHABLE}" WITH (FORCE)'
    try:
        try:
            await conexion.execute(tirar)
            await conexion.execute(f'CREATE DATABASE "{BASE_DESECHABLE}"')
        except asyncpg.PostgresError as fallo:
            # Sin permiso para crear bases, o con la plantilla ocupada: no hay
            # donde migrar desde cero y eso no dice nada del codigo. Se salta
            # con el motivo del servidor dentro.
            pytest.skip(f"No se pudo crear la base desechable: {fallo}")
        try:
            yield _con_base(url_de_la_suite, BASE_DESECHABLE)
        finally:
            await conexion.execute(tirar)
    finally:
        await conexion.close()


@pytest.mark.asyncio
async def test_una_instalacion_nueva_nace_con_su_catalogo(base_recien_nacida, tmp_path):
    """El camino del despliegue: migrar desde cero y arrancar por primera vez.

    Le pasaria a `testeo.tech` o a cualquier entorno nuevo, y no a la base de
    Eduardo, que ya tenia el catalogo de antes y migrarla lo conservo.
    """
    _migrar(base_recien_nacida, "head")

    # Se lee antes de arrancar porque despues ya lo sembro `ensure_catalogs()`.
    cabeceras_tras_migrar = (await _consultar(base_recien_nacida, _CONTEOS))[0]["poas"]

    # El primer arranque, como lo hace `app/core/lifecycle.py`: el `lifespan`
    # es quien llama a `ensure_catalogs()`.
    aplicacion = create_app(
        Settings(
            environment="testing",
            indicators_module_enabled=True,
            database_url=base_recien_nacida,
            email_provider="console",
            secret_key="test-secret-key-with-more-than-32-characters",
            upload_directory=str(tmp_path),
        )
    )
    async with aplicacion.router.lifespan_context(aplicacion):
        pass

    conteos = dict((await _consultar(base_recien_nacida, _CONTEOS))[0])
    assert conteos == CATALOGO_DEL_PRIMER_ARRANQUE

    # La razon, por si lo de arriba se rompe: migrar no puede dejar una cabecera
    # puesta en una instalacion nueva. Existe para apropiarse de lo que ya
    # estaba, y aqui no hay nada que apropiarse; si se pone igual,
    # `ensure_catalogs()` la encuentra, se da por sembrada y no siembra.
    assert cabeceras_tras_migrar == 0, "migrar desde cero no deja ningun POA que adoptar"

    duenos = [fila["catalogo_id"] for fila in await _consultar(base_recien_nacida, _DUENOS)]
    cabeceras = await _consultar(base_recien_nacida, "SELECT id FROM poa_catalogos ORDER BY id")
    assert duenos == [fila["id"] for fila in cabeceras], "el catalogo cuelga del unico POA que hay"


@pytest.mark.asyncio
async def test_migrar_con_catalogo_que_adoptar_sigue_poniendole_cabecera(base_recien_nacida):
    """La otra rama de la condicion: donde si hay algo que adoptar, la cabecera
    se pone igual que antes y el catalogo que ya estaba queda colgando de ella.

    Es el camino por el que la 0037 ya paso en las dos bases locales, y es la
    razon por la que volver el `INSERT` condicional no divergio de lo aplicado.
    Sin esta prueba, apretar la condicion de mas -o escribirla al reves- rompe
    la actualizacion de una instalacion viva y nada lo avisa: lo de arriba
    seguiria pasando, porque ahi no hay catalogo previo.
    """
    _migrar(base_recien_nacida, "0036_catalogo_pse_administrable")
    await _sembrar(base_recien_nacida, CATALOGO_DE_ANTES)
    _migrar(base_recien_nacida, "head")

    cabeceras = await _consultar(
        base_recien_nacida, "SELECT id, nombre, anio FROM poa_catalogos ORDER BY id"
    )
    assert [(fila["nombre"], fila["anio"]) for fila in cabeceras] == [("POA 2026", 2026)]

    conteos = dict((await _consultar(base_recien_nacida, _CONTEOS))[0])
    assert conteos == {"poas": 1, "objetivos": 1, "estrategias": 1, "indicadores": 1, "acciones": 1}

    duenos = [fila["catalogo_id"] for fila in await _consultar(base_recien_nacida, _DUENOS)]
    assert duenos == [cabeceras[0]["id"]], "lo que ya estaba quedo colgando de la cabecera"
