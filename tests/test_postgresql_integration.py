from __future__ import annotations

import asyncio
import os
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings, get_settings
from app.main import create_app
from app.modules.evidence_management.domain.entities import Evidence, EvidenceVersion
from app.modules.evidence_management.domain.value_objects import EvidenceType
from app.modules.evidence_management.infrastructure.models import EvidenceModel
from app.modules.evidence_management.infrastructure.sql_repository import (
    SqlAlchemyEvidenceRepository,
)
from app.modules.identity_access.application.dto import RegisterUserCommand
from app.modules.identity_access.application.use_cases.create_user import CreateUser
from app.modules.identity_access.domain.value_objects import Role
from app.modules.identity_access.infrastructure.models import RefreshTokenModel
from app.modules.identity_access.infrastructure.revoked_token_store import (
    SqlAlchemyRevokedTokenStore,
)
from app.modules.identity_access.infrastructure.sql_repository import (
    SqlAlchemyRefreshTokenStore,
)
from app.scripts.seed_integration import seed
from app.shared.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWorkFactory

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL no configurada")
@pytest.mark.asyncio
async def test_postgresql_migrations_uow_rollback_and_persistent_revocation():
    engine = create_async_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex
    async with engine.begin() as connection:
        user_id = await connection.scalar(
            text(
                """
                INSERT INTO usuarios (nombre, correo, hash_password)
                VALUES (:name, :email, :password)
                RETURNING id
                """
            ),
            {
                "name": "Prueba transaccion",
                "email": f"uow-{suffix}@upchiapas.edu.mx",
                "password": "test-only-hash",
            },
        )
        version_column = await connection.scalar(
            text(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'indicadores' AND column_name = 'version'
                """
            )
        )
        assert version_column == 1

    repository = SqlAlchemyEvidenceRepository(factory)
    evidence = Evidence.create(
        name=f"rollback-{suffix}",
        description="Debe revertirse por completo",
        evidence_date=date.today(),
        evidence_type=EvidenceType.LINK,
        uploaded_by=user_id,
    )
    with pytest.raises(RuntimeError, match="forced rollback"):
        async with SqlAlchemyUnitOfWorkFactory(factory)():
            await repository.add(evidence)
            await repository.add_version(
                EvidenceVersion(
                    evidence_id=evidence.id,
                    path_or_url=f"https://example.com/{suffix}",
                    mime_type=None,
                    size_bytes=None,
                    checksum_sha256=None,
                    user_id=user_id,
                    created_at=datetime.now(UTC),
                )
            )
            raise RuntimeError("forced rollback")
    async with factory() as session:
        assert (
            await session.scalar(
                select(EvidenceModel.id).where(EvidenceModel.nombre == evidence.name)
            )
            is None
        )

    token_id = uuid4()
    await SqlAlchemyRevokedTokenStore(factory).revoke(
        token_id, datetime.now(UTC) + timedelta(minutes=5)
    )
    assert await SqlAlchemyRevokedTokenStore(factory).is_revoked(token_id)

    session_id = uuid4()
    original_id = uuid4()
    expires_at = datetime.now(UTC) + timedelta(days=1)
    await SqlAlchemyRefreshTokenStore(factory).save(
        token="refresh-original",
        token_id=original_id,
        user_id=user_id,
        session_id=session_id,
        expires_at=expires_at,
    )
    first_store = SqlAlchemyRefreshTokenStore(factory)
    second_store = SqlAlchemyRefreshTokenStore(factory)
    first, second = await asyncio.gather(
        first_store.rotate(
            current_token="refresh-original",
            current_token_id=original_id,
            new_token="refresh-a",
            new_token_id=uuid4(),
            user_id=user_id,
            session_id=session_id,
            expires_at=expires_at,
        ),
        second_store.rotate(
            current_token="refresh-original",
            current_token_id=original_id,
            new_token="refresh-b",
            new_token_id=uuid4(),
            user_id=user_id,
            session_id=session_id,
            expires_at=expires_at,
        ),
    )
    assert first is not None and second is not None
    assert sorted((first.active, second.active)) == [False, True]
    async with factory() as session:
        active_descendants = await session.scalar(
            select(func.count())
            .select_from(RefreshTokenModel)
            .where(
                RefreshTokenModel.session_id == session_id,
                RefreshTokenModel.revocado_en.is_(None),
            )
        )
    assert active_descendants == 0
    await engine.dispose()


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL no configurada")
@pytest.mark.asyncio
async def test_postgresql_seed_and_frontend_read_contracts(monkeypatch):
    seed_password = "integration-test-password-only"
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL or "")
    monkeypatch.setenv("SEED_TEST_PASSWORD", seed_password)
    get_settings.cache_clear()
    await seed()

    application = create_app(
        Settings(
            environment="testing",
            indicators_module_enabled=True,
            secret_key="test-secret-key-with-more-than-32-characters",
            database_url=TEST_DATABASE_URL,
            email_provider="console",
        )
    )
    try:
        async with AsyncClient(
            transport=ASGITransport(app=application),
            base_url="http://testserver",
        ) as client:
            login = await client.post(
                "/api/v1/auth/login",
                json={
                    "correo": "admin.sistema@upchiapas.edu.mx",
                    "contrasena": seed_password,
                },
            )
            assert login.status_code == 200
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

            indicators = await client.get(
                "/api/v1/indicadores?sort=actualizado_en&order=desc&limit=10",
                headers=headers,
            )
            assert indicators.status_code == 200
            assert indicators.json()["total"] >= 5

            captures = await client.get(
                "/api/v1/capturas?sort=indicador&order=asc&limit=10",
                headers=headers,
            )
            assert captures.status_code == 200
            capture_rows = captures.json()["items"]
            assert capture_rows
            assert {"indicador", "periodo", "area", "capturista"}.issubset(
                capture_rows[0]
            )

            with_evidence = next(row for row in capture_rows if row["evidencias_total"] > 0)
            evidences = await client.get(
                f"/api/v1/capturas/{with_evidence['id']}/evidencias",
                headers=headers,
            )
            assert evidences.status_code == 200
            assert evidences.json()[0]["version_actual"]["ruta_o_url"]

            users = await client.get("/api/v1/usuarios?limit=10", headers=headers)
            assert users.status_code == 200
            assert {"area_nombre", "ultimo_acceso", "notificar_correo", "version"}.issubset(
                users.json()["items"][0]
            )
    finally:
        await application.state.db_engine.dispose()
        get_settings.cache_clear()


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL no configurada")
@pytest.mark.asyncio
async def test_postgresql_directory_roles_and_form_quarter_transaction():
    application = create_app(
        Settings(
            environment="testing",
            indicators_module_enabled=True,
            secret_key="test-secret-key-with-more-than-32-characters",
            database_url=TEST_DATABASE_URL,
            email_provider="console",
        )
    )
    suffix = uuid4().hex[:8]
    try:
        await application.state.poa_form_repository.ensure_catalogs()
        await CreateUser(
            repository=application.state.user_repository,
            password_hasher=application.state.password_hasher,
            event_bus=application.state.event_bus,
        ).execute(
            RegisterUserCommand(
                email=f"admin-cedula-{suffix}@upchiapas.edu.mx",
                full_name="Administrador de prueba",
                password="password-seguro",
                roles={
                    Role.PLANEACION_ADMIN,
                    Role.CAPTURISTA_POA,
                    Role.REVISOR_POA,
                },
                area_id=None,
            )
        )
        async with AsyncClient(
            transport=ASGITransport(app=application),
            base_url="http://testserver",
        ) as client:
            login = await client.post(
                "/api/v1/auth/login",
                json={
                    "correo": f"admin-cedula-{suffix}@upchiapas.edu.mx",
                    "contrasena": "password-seguro",
                },
            )
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
            invited = await client.post(
                "/api/v1/usuarios",
                json={
                    "correo": "hdelacruz@upchiapas.edu.mx",
                    "nombre": "Cuenta de Programación y Presupuesto",
                },
                headers=headers,
            )
            assert invited.status_code == 201, invited.text
            assert invited.json()["roles"] == ["capturista_poa"]
            assert invited.json()["area_nombre"] == (
                "Dirección de Programación y Presupuesto"
            )

            area = await client.post(
                "/api/v1/catalogos/areas",
                json={"codigo": f"SQL-{suffix}", "nombre": f"Área SQL {suffix}"},
                headers=headers,
            )
            exercise = await client.post(
                "/api/v1/poa/ejercicios",
                json={"anio": 2198},
                headers=headers,
            )
            form = await client.post(
                "/api/v1/poa/cedulas",
                json={
                    "ejercicio_id": exercise.json()["id"],
                    "estrategia_clave": "1.1",
                    "area_responsable_id": area.json()["id"],
                    "cuatrimestres": [
                        {
                            "numero": 1,
                            "fecha_inicio": "2198-01-10",
                            "fecha_fin": "2198-04-20",
                        },
                        {
                            "numero": 2,
                            "fecha_inicio": "2198-05-05",
                            "fecha_fin": "2198-08-25",
                        },
                        {
                            "numero": 3,
                            "fecha_inicio": "2198-09-03",
                            "fecha_fin": "2198-12-15",
                        },
                    ],
                },
                headers=headers,
            )
            assert form.status_code == 201, form.text
            assert len(form.json()["cuatrimestres"]) == 3
            assert all(item["periodo_id"] for item in form.json()["cuatrimestres"])
            updated_form = await client.patch(
                f"/api/v1/poa/cedulas/{form.json()['id']}",
                json={"alcance_efecto_socioeconomico": "Corrección administrativa"},
                headers=headers,
            )
            assert updated_form.status_code == 200, updated_form.text
            assert updated_form.json()["version"] == 2

            indicator = await client.post(
                f"/api/v1/poa/cedulas/{form.json()['id']}/indicadores",
                json={"indicador_clave": "1.1.14", "meta_institucional": 10},
                headers=headers,
            )
            assert indicator.status_code == 201, indicator.text
            updated_indicator = await client.patch(
                f"/api/v1/poa/cedulas/indicadores/{indicator.json()['id']}",
                json={"meta_institucional": 12},
                headers=headers,
            )
            assert updated_indicator.status_code == 200, updated_indicator.text
            assert Decimal(updated_indicator.json()["meta_institucional"]) == Decimal("12")
    finally:
        await application.state.db_engine.dispose()
