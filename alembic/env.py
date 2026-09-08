"""Configuracion de Alembic; el DDL real vive en bd/migrations."""

from __future__ import annotations

import asyncio
from importlib import import_module
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings
from app.shared.infrastructure.db.base import Base

for _model_module in (
    "app.modules.audit.infrastructure.models",
    "app.modules.identity_access.infrastructure.models",
    "app.modules.indicators_catalog.infrastructure.models",
    "app.modules.evidence_management.infrastructure.models",
    "app.modules.indicators_capture.infrastructure.models",
    "app.modules.indicators_validation.infrastructure.models",
    "app.modules.indicators_reports.infrastructure.models",
    "app.modules.poa_planning.infrastructure.models",
    "app.modules.poa_planning.infrastructure.cedula_models",
    "app.modules.notifications.infrastructure.models",
    "app.modules.institutional_catalogs.infrastructure.models",
    "app.modules.periods.infrastructure.models",
):
    import_module(_model_module)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_object(obj, name, type_, reflected, compare_to):
    # Tablas históricas no mapeadas: nunca proponer borrarlas mediante autogenerate.
    if type_ == "table" and reflected and compare_to is None and name in {
        "poa_procesos", "poa_objetivos", "poa_actividades", "poa_avances",
        "poa_avance_criterios", "poa_avance_criterios_seaes",
    }:
        return False
    return True


def _database_url() -> str:
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL debe configurarse para ejecutar Alembic.")
    if settings.database_url.startswith("postgresql://"):
        return settings.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return settings.database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        include_object=include_object,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection, target_metadata=target_metadata, include_object=include_object
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url()
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
