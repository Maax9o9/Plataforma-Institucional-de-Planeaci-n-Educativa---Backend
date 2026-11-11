from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url

from app.core.config import Settings
from app.main import create_app
from app.modules.identity_access.application.dto import RegisterUserCommand
from app.modules.identity_access.application.use_cases.create_user import CreateUser
from app.modules.identity_access.domain.value_objects import Role
from app.modules.institutional_catalogs.domain.entities import Area

# `tests/helpers.py` no es un archivo de prueba, asi que pytest no reescribe
# sus aserciones por su cuenta: un `assert creada.status_code == 201` que falla
# dentro de un ayudante mostraba `AssertionError: <el cuerpo de la respuesta>`
# en vez de `assert 500 == 201`. Pedirlo aqui -antes de que cualquier modulo de
# prueba importe `helpers`- devuelve el mensaje que dice que se comparaba.
pytest.register_assert_rewrite("helpers")

# Tablas con datos sembrados por una migracion (no por las pruebas). Si se
# vaciaran junto con el resto, nada las repuebla: `unidades_medida` perderia
# las veinte claves de la migracion 0032 y `alembic_version` perderia el
# historial de versiones aplicadas.
_TABLAS_SEMBRADAS_POR_MIGRACION = frozenset({"alembic_version", "unidades_medida"})


PLANTILLA_DE_LA_BASE_DE_PRUEBAS = os.getenv("TEST_DATABASE_URL")


def _dsn(url: URL) -> str:
    sin_el_driver = url.render_as_string(hide_password=False)
    return sin_el_driver.replace("postgresql+asyncpg://", "postgresql://")


async def _en_el_servidor(url: URL, *sentencias: str) -> None:
    connection = await asyncpg.connect(_dsn(url.set(database="postgres")))
    try:
        for sentencia in sentencias:
            await connection.execute(sentencia)
    finally:
        await connection.close()


async def _vaciar(url: URL) -> None:
    connection = await asyncpg.connect(_dsn(url))
    try:
        filas = await connection.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        )
        tablas = [
            fila["tablename"]
            for fila in filas
            if fila["tablename"] not in _TABLAS_SEMBRADAS_POR_MIGRACION
        ]
        if not tablas:
            return
        listado = ", ".join(f'"{tabla}"' for tabla in tablas)
        await connection.execute(f"TRUNCATE TABLE {listado} RESTART IDENTITY CASCADE")
        # `config_sistema` es una fila unica (chk_fila_unica) sembrada por
        # la migracion 0003; el TRUNCATE de arriba la vacia (referencia a
        # `usuarios`, que si se trunca). Se repone para dejarla como recien
        # migrada.
        await connection.execute("INSERT INTO config_sistema (id) VALUES (1)")
    finally:
        await connection.close()


OBJETIVOS_Y_ESTRATEGIAS_DEL_POA_SEMBRADO = (6, 24)


# El pozo de años de ejercicio. `poa_ejercicios.anio` es unico en todo el
# sistema y el dominio solo admite 2000..2200, o sea **201 anios para toda una
# sesion de pytest**. Medido en 4a1aa20 con la suite completa: 196 tomados y 5
# libres (2195, 2196, 2197, 2198 y 2200). Es decir, a seis pruebas de la pared;
# y el fallo no se lee como «se acabaron los anios» sino como una prueba de
# reportes que nadie toco.
#
# Lo que lo arregla es devolver lo prestado. De los 196, 160 terminaban la
# sesion **sin nada colgando**: ejercicios que su prueba creo, uso y no volvio a
# mirar. Los otros 36 sostienen cedulas. Asi que al terminar cada prueba de la
# variante de PostgreSQL se borran los ejercicios prestados que no sostienen
# nada, y los que si sostienen algo se quedan donde estan: borrarlos seria el
# arnes reimplementando el borrado en cascada de una cedula, y de paso el
# defecto de tocar datos de los que otra prueba afirma algo.
#
# Las tablas hijas **no van escritas aqui**: se preguntan al catalogo de
# PostgreSQL en cada vuelta. Una llave foranea nueva hacia `poa_ejercicios`
# -hoy son `poa_procesos`, `poa_cedulas` y `poa_inst_areas`- entra sola en la
# guarda; escrita a mano, la siguiente migracion la dejaria fuera y el DELETE
# reventaria con una violacion de llave foranea en el desmontaje de una prueba
# cualquiera.
_LAS_HIJAS_DE_LOS_EJERCICIOS = """
SELECT c.conname,
       hija.attname  AS columna_hija,
       padre.attname AS columna_del_ejercicio,
       c.conrelid::regclass::text AS tabla_hija
FROM pg_constraint c
JOIN LATERAL unnest(c.conkey, c.confkey) AS par(hijo, padre) ON true
JOIN pg_attribute hija  ON hija.attrelid  = c.conrelid  AND hija.attnum  = par.hijo
JOIN pg_attribute padre ON padre.attrelid = c.confrelid AND padre.attnum = par.padre
WHERE c.contype = 'f' AND c.confrelid = 'poa_ejercicios'::regclass
"""


async def _guarda_de_lo_que_sostiene_algo(conexion) -> str:
    por_restriccion: dict[str, list[tuple[str, str, str]]] = {}
    for fila in await conexion.execute(text(_LAS_HIJAS_DE_LOS_EJERCICIOS)):
        por_restriccion.setdefault(fila.conname, []).append(
            (fila.tabla_hija, fila.columna_hija, fila.columna_del_ejercicio)
        )
    guardas = []
    for columnas in por_restriccion.values():
        tabla = columnas[0][0]
        iguales = " AND ".join(
            f"hija.{hija} = e.{del_ejercicio}" for _, hija, del_ejercicio in columnas
        )
        guardas.append(f"NOT EXISTS (SELECT 1 FROM {tabla} hija WHERE {iguales})")
    return " AND ".join(guardas) if guardas else "true"


async def devolver_los_anios_al_pozo(motor, anios: set[int]) -> set[int]:
    """Borra los ejercicios de `anios` que no sostienen nada, y devuelve los
    años que quedaron libres.

    Se le pasa el motor de la aplicación de la prueba y no una conexión propia
    porque ese motor ya está abierto: una conexión nueva por prueba son mil
    conexiones más en una corrida.
    """
    if not anios:
        return set()
    async with motor.begin() as conexion:
        guarda = await _guarda_de_lo_que_sostiene_algo(conexion)
        devueltos = await conexion.execute(
            text(
                "DELETE FROM poa_ejercicios e WHERE e.anio = ANY(:anios) "
                f"AND {guarda} RETURNING e.anio"
            ),
            {"anios": sorted(anios)},
        )
        return {fila.anio for fila in devueltos}


def _la_copia_de_esta_sesion() -> URL:
    plantilla = make_url(PLANTILLA_DE_LA_BASE_DE_PRUEBAS)
    return plantilla.set(database=f"{plantilla.database}_{os.getpid()}")


async def _lo_que_queda_del_poa_sembrado(url: URL) -> tuple[int, int] | None:
    connection = await asyncpg.connect(_dsn(url))
    try:
        sembrado = await connection.fetchval(
            "SELECT id FROM poa_catalogos WHERE nombre = 'POA 2026'"
        )
        if sembrado is None:
            return None
        return (
            await connection.fetchval(
                "SELECT count(*) FROM poa_catalogo_objetivos WHERE catalogo_id = $1", sembrado
            ),
            await connection.fetchval(
                "SELECT count(*) FROM poa_catalogo_estrategias WHERE catalogo_id = $1", sembrado
            ),
        )
    finally:
        await connection.close()


@pytest.fixture(scope="session", autouse=True)
def _el_poa_sembrado_sigue_siendo_el_sembrado_al_terminar_la_suite():
    yield
    if not PLANTILLA_DE_LA_BASE_DE_PRUEBAS:
        return
    quedo = asyncio.run(_lo_que_queda_del_poa_sembrado(_la_copia_de_esta_sesion()))
    if quedo is None:
        return
    assert quedo == OBJETIVOS_Y_ESTRATEGIAS_DEL_POA_SEMBRADO, (
        f"La suite dejo «POA 2026» con {quedo[0]} objetivos y {quedo[1]} estrategias en vez de "
        f"{OBJETIVOS_Y_ESTRATEGIAS_DEL_POA_SEMBRADO}: alguna prueba formulo sobre el POA "
        "sembrado en vez de crear el suyo con `crear_poa()`, y las que afirman algo sobre el "
        "POA inicial pasan o fallan segun el orden alfabetico de los archivos."
    )


#: Cuántos años del pozo tienen que quedar libres al terminar la suite completa.
#: Medido el 4 de noviembre de 2026: sin devolver nada quedaban **5** de 201, y
#: devolviendo lo que no sostiene nada quedan **157** -44 tomados: 36 ejercicios
#: con cédula, siete años fijos y el 2200 de la prueba del mensaje-.
#:
#: El umbral está en 75 y no más arriba porque la condición que esto defiende es
#: que la suite pueda crecer en cincuenta pruebas con ejercicio: medido, esas
#: cincuenta -la mitad con cédula- dejan 132 libres, así que avisa mucho antes de
#: la pared y no le estorba al crecimiento previsto.
#:
#: Si salta, lo que creció no es el techo: es lo que la suite deja **colgando**
#: de un ejercicio, porque lo que no sostiene nada se devuelve solo.
ANIOS_DE_EJERCICIO_QUE_TIENEN_QUE_QUEDAR_LIBRES = 75


async def _anios_de_ejercicio_tomados(url: URL) -> int:
    connection = await asyncpg.connect(_dsn(url))
    try:
        return await connection.fetchval("SELECT count(*) FROM poa_ejercicios")
    finally:
        await connection.close()


@pytest.fixture(scope="session", autouse=True)
def _al_pozo_de_anios_de_ejercicio_le_sobra_sitio_al_terminar_la_suite():
    """La canaria del pozo: avisa mientras todavía hay salida.

    `anio_libre` dice la verdad cuando el pozo ya está seco, y eso es tarde:
    rompe la prueba que pidió el año -medido, tres de `test_reportes_poa.py`- y
    no la que gastó el pozo. Esto mira el saldo al terminar la sesión, que es el
    único sitio donde se ve: por archivo nunca se agota.
    """
    yield
    if not PLANTILLA_DE_LA_BASE_DE_PRUEBAS:
        return
    import helpers

    del_contrato = helpers.ULTIMO_ANIO_DEL_CONTRATO - helpers.PRIMER_ANIO_DEL_CONTRATO + 1
    tomados = asyncio.run(_anios_de_ejercicio_tomados(_la_copia_de_esta_sesion()))
    libres = del_contrato - tomados
    assert libres >= ANIOS_DE_EJERCICIO_QUE_TIENEN_QUE_QUEDAR_LIBRES, (
        f"Al pozo de años de ejercicio le quedan {libres} libres de {del_contrato}, y el "
        f"mínimo es {ANIOS_DE_EJERCICIO_QUE_TIENEN_QUE_QUEDAR_LIBRES}. Cuando lleguen a "
        "cero no fallará la prueba que gastó el pozo sino la siguiente que pida un año. "
        "Lo que se queda tomado es lo que sostiene algo -una cédula- o lo que pide un "
        f"año fijo; el {helpers.ULTIMO_ANIO_DEL_CONTRATO} es del dominio y no se ensancha."
    )


def pytest_sessionstart(session) -> None:
    if not PLANTILLA_DE_LA_BASE_DE_PRUEBAS:
        return
    copia = _la_copia_de_esta_sesion()
    asyncio.run(
        _en_el_servidor(
            copia,
            f'DROP DATABASE IF EXISTS "{copia.database}"',
            f'CREATE DATABASE "{copia.database}" '
            f'TEMPLATE "{make_url(PLANTILLA_DE_LA_BASE_DE_PRUEBAS).database}"',
        )
    )
    os.environ["TEST_DATABASE_URL"] = copia.render_as_string(hide_password=False)
    asyncio.run(_vaciar(copia))


def pytest_sessionfinish(session, exitstatus) -> None:
    if not PLANTILLA_DE_LA_BASE_DE_PRUEBAS:
        return
    copia = _la_copia_de_esta_sesion()
    os.environ["TEST_DATABASE_URL"] = PLANTILLA_DE_LA_BASE_DE_PRUEBAS
    asyncio.run(_en_el_servidor(copia, f'DROP DATABASE IF EXISTS "{copia.database}" WITH (FORCE)'))


@pytest.fixture(autouse=True)
def _el_pozo_de_anios_empieza_sin_prestamos():
    """Ninguna prueba hereda los préstamos de la anterior.

    Importa `helpers` aquí dentro y no arriba porque `pytest_register_assert_rewrite`
    sólo reescribe un módulo que todavía no se ha importado: importarlo en la
    cabecera de este archivo deja a `helpers` sin reescritura de aserciones.

    El vaciado va antes **y** después porque la variante de memoria también pide
    años -y los pide a su propio almacén, que nace vacío en cada prueba, así que
    siempre le toca el 2000-. Si esos préstamos sobrevivieran a la prueba, la
    siguiente de PostgreSQL intentaría devolver al pozo un 2000 que no es suyo.
    """
    import helpers

    helpers.ANIOS_PRESTADOS.clear()
    yield
    helpers.ANIOS_PRESTADOS.clear()


@pytest.fixture(params=["memory", "postgresql"])
async def backend_client(request, tmp_path):
    import helpers

    database_url = None
    if request.param == "postgresql":
        database_url = os.getenv("TEST_DATABASE_URL")
        if not database_url:
            pytest.skip("TEST_DATABASE_URL no configurada")
    application = create_app(
        Settings(
            environment="testing",
            monthly_cycle_enabled=True,
            database_url=database_url,
            email_provider="console",
            secret_key="test-secret-key-with-more-than-32-characters",
            upload_directory=str(tmp_path),
        )
    )
    try:
        await application.state.poa_form_repository.ensure_catalogs()
        async with AsyncClient(
            transport=ASGITransport(app=application), base_url="http://testserver"
        ) as client:
            yield application, client
    finally:
        await application.state.notification_service.close()
        if application.state.db_engine is not None:
            await devolver_los_anios_al_pozo(
                application.state.db_engine, set(helpers.ANIOS_PRESTADOS)
            )
            await application.state.db_engine.dispose()


async def cabeceras_de_una_cuenta(
    backend_client, rol: Role, *, area_id: int | None
) -> dict[str, str]:
    app, client = backend_client
    correo = f"{rol.value}-{uuid4().hex[:8]}@example.com"
    await CreateUser(
        app.state.user_repository, app.state.password_hasher, app.state.event_bus
    ).execute(
        RegisterUserCommand(
            email=correo,
            full_name=f"Cuenta de pruebas con rol {rol.value}",
            password="password-seguro",
            roles={rol},
            area_id=area_id,
        )
    )
    login = await client.post(
        "/api/v1/auth/login", json={"correo": correo, "contrasena": "password-seguro"}
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.fixture
async def planeacion_headers(backend_client) -> dict[str, str]:
    """Las cabeceras de una cuenta de Planeación recién creada.

    Trabaja con la aplicación y el cliente de `backend_client`, así que corre
    en las dos variantes (memoria y PostgreSQL) sin crear una aplicación propia.
    El correo lleva sufijo único porque la base de PostgreSQL persiste durante
    la corrida y los correos son únicos.

    Esta cuenta no tiene área y Planeación está exenta de la guarda por área,
    así que una prueba de autorización por área escrita sólo con ella pasa sin
    comparar nunca un área: para eso están `capturista_de_su_area_headers` y
    `capturista_sin_area_headers`.
    """
    return await cabeceras_de_una_cuenta(backend_client, Role.PLANEACION, area_id=None)


@pytest.fixture
def nueva_area(backend_client):
    app, _ = backend_client

    async def crear() -> int:
        area = Area.create(
            code=f"PRUEBA-{uuid4().hex[:8]}", name=f"Área de pruebas {uuid4().hex[:8]}"
        )
        await app.state.area_repository.add(area)
        return area.id

    return crear


@pytest.fixture
def cuenta_con_rol(backend_client):
    async def crear(rol: Role, *, area_id: int | None) -> dict[str, str]:
        return await cabeceras_de_una_cuenta(backend_client, rol, area_id=area_id)

    return crear


@pytest.fixture
async def area_propia(nueva_area) -> int:
    return await nueva_area()


@pytest.fixture
async def capturista_de_su_area_headers(backend_client, area_propia) -> dict[str, str]:
    return await cabeceras_de_una_cuenta(backend_client, Role.CAPTURISTA_POA, area_id=area_propia)


@pytest.fixture
async def capturista_sin_area_headers(backend_client) -> dict[str, str]:
    return await cabeceras_de_una_cuenta(backend_client, Role.CAPTURISTA_POA, area_id=None)


@pytest.fixture
def app():
    return create_app(
        Settings(
            environment="testing",
            monthly_cycle_enabled=True,
            secret_key="test-secret-key-with-more-than-32-characters",
            database_url=None,
            email_provider="console",
            bootstrap_admin_email=None,
            bootstrap_admin_password=None,
        )
    )


@pytest.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as async_client:
        yield async_client
