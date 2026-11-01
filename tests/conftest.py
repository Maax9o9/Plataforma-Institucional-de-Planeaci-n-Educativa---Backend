from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient
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


@pytest.fixture(params=["memory", "postgresql"])
async def backend_client(request, tmp_path):
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
