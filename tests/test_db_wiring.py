from __future__ import annotations

import pytest

from app.core.config import Settings
from app.main import create_app
from app.modules.audit.infrastructure.sql_repository import SqlAlchemyAuditRepository
from app.modules.identity_access.infrastructure.sql_repository import (
    SqlAlchemyRefreshTokenStore,
    SqlAlchemyUserRepository,
)
from app.modules.institutional_catalogs.infrastructure.sql_repository import (
    SqlAlchemyAreaRepository,
    SqlAlchemyInstrumentRepository,
)
from app.modules.periods.infrastructure.sql_repository import SqlAlchemyPeriodRepository


def database_settings() -> Settings:
    return Settings(
        environment="testing",
            indicators_module_enabled=True,
        secret_key="test-secret-key-with-more-than-32-characters",
        database_url="postgresql+asyncpg://planeacion:planeacion_dev@localhost:5433/planeacion",
        email_provider="console",
        cors_origins=["http://localhost:5173"],
    )


@pytest.mark.asyncio
async def test_database_url_selects_sqlalchemy_adapters_without_connecting():
    app = create_app(database_settings())
    try:
        assert isinstance(app.state.user_repository, SqlAlchemyUserRepository)
        assert isinstance(app.state.refresh_token_store, SqlAlchemyRefreshTokenStore)
        assert isinstance(app.state.area_repository, SqlAlchemyAreaRepository)
        assert isinstance(app.state.instrument_repository, SqlAlchemyInstrumentRepository)
        assert isinstance(app.state.period_repository, SqlAlchemyPeriodRepository)
        assert isinstance(app.state.audit_repository, SqlAlchemyAuditRepository)
    finally:
        await app.state.db_engine.dispose()


def test_sqlalchemy_models_describe_owned_tables():
    from importlib import import_module

    from app.shared.infrastructure.db.base import Base

    for module_name in (
        "app.modules.audit.infrastructure.models",
        "app.modules.identity_access.infrastructure.models",
        "app.modules.institutional_catalogs.infrastructure.models",
        "app.modules.periods.infrastructure.models",
        "app.modules.poa_planning.infrastructure.cedula_models",
    ):
        import_module(module_name)

    expected_tables = {
        "usuarios",
        "usuario_roles",
        "refresh_tokens",
        "areas",
        "instrumentos",
        "periodos",
        "indicadores",
        "capturas",
        "evidencias",
        "cambios_estado",
        "bitacora",
        "reportes_generados",
        "poa_catalogo_objetivos",
        "poa_catalogo_estrategias",
        "poa_catalogo_indicadores",
        "poa_catalogo_actividades",
        "poa_cedulas",
        "poa_cedula_indicadores",
        "poa_cedula_cuatrimestres",
        "poa_cedula_actividades",
        "poa_cedula_seguimientos",
        "poa_cedula_emisiones",
    }
    assert expected_tables.issubset(Base.metadata.tables)
