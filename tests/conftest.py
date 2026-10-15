from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app
from app.modules.identity_access.application.dto import RegisterUserCommand
from app.modules.identity_access.application.use_cases.create_user import CreateUser
from app.modules.identity_access.domain.value_objects import Role

# Tablas con datos sembrados por una migracion (no por las pruebas). Si se
# vaciaran junto con el resto, nada las repuebla: `unidades_medida` perderia
# las veinte claves de la migracion 0032 y `alembic_version` perderia el
# historial de versiones aplicadas.
_TABLAS_SEMBRADAS_POR_MIGRACION = frozenset({"alembic_version", "unidades_medida"})


@pytest.fixture(scope="session", autouse=True)
def _base_postgresql_de_pruebas_limpia() -> None:
    """Deja `TEST_DATABASE_URL` como recien migrada, sin recrearla.

    La suite corre contra una base de Postgres real y persistente: crea
    usuarios con correos fijos, ejercicios POA con `anio` unico, etc. Si esos
    datos sobreviven de una corrida a otra, las pruebas empiezan a chocar
    entre si -correos duplicados, el rango 2000-2200 de anios agotandose- y
    dos de esos choques se llegaron a reportar como fallas preexistentes sin
    serlo. Vaciar las tablas de la aplicacion una sola vez, al arrancar la
    sesion de pytest, reproduce el estado de una base recien migrada en cada
    corrida sin depender de que alguien la recree a mano antes de correr.
    """
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        return

    dsn = database_url.replace("postgresql+asyncpg://", "postgresql://")

    async def _vaciar() -> None:
        connection = await asyncpg.connect(dsn)
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

    asyncio.run(_vaciar())


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
            indicators_module_enabled=True,
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


@pytest.fixture
async def planeacion_headers(backend_client) -> dict[str, str]:
    """Las cabeceras de una cuenta de Planeación recién creada.

    Trabaja con la aplicación y el cliente de `backend_client`, así que corre
    en las dos variantes (memoria y PostgreSQL) sin crear una aplicación propia.
    El correo lleva sufijo único porque la base de PostgreSQL persiste durante
    la corrida y los correos son únicos.
    """
    app, client = backend_client
    correo = f"planeacion-{uuid4().hex[:8]}@example.com"
    await CreateUser(
        app.state.user_repository, app.state.password_hasher, app.state.event_bus
    ).execute(
        RegisterUserCommand(
            email=correo,
            full_name="Planeación de pruebas",
            password="password-seguro",
            roles={Role.PLANEACION},
            area_id=None,
        )
    )
    login = await client.post(
        "/api/v1/auth/login", json={"correo": correo, "contrasena": "password-seguro"}
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def poa_inicial_id(client, headers) -> int:
    """El id del POA que siembra el sistema, para las pruebas que sólo necesitan
    *un* POA del que colgar un ejercicio.

    Se pide por el nombre y por la API, no por el repositorio: así sirve igual
    en cualquier variante, y a quien sólo tiene cliente y cabeceras en la mano.
    """
    listado = await client.get("/api/v1/poa/catalogos-poa", headers=headers)
    assert listado.status_code == 200, listado.text
    return next(poa["id"] for poa in listado.json() if poa["nombre"] == "POA 2026")


@pytest.fixture
def app():
    return create_app(
        Settings(
            environment="testing",
            indicators_module_enabled=True,
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
