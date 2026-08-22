from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.evidence_management.domain.entities import Evidence, EvidenceVersion
from app.modules.evidence_management.domain.value_objects import EvidenceType
from app.modules.evidence_management.infrastructure.models import EvidenceModel
from app.modules.evidence_management.infrastructure.sql_repository import (
    SqlAlchemyEvidenceRepository,
)
from app.modules.identity_access.infrastructure.revoked_token_store import (
    SqlAlchemyRevokedTokenStore,
)
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
    await engine.dispose()
