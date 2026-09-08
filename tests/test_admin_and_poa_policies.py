import os
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.identity_access.domain.value_objects import Role
from app.modules.identity_access.infrastructure.security import Argon2PasswordHasher
from app.modules.identity_access.infrastructure.sql_repository import SqlAlchemyUserRepository
from app.modules.institutional_catalogs.domain.entities import Area
from app.modules.poa_planning.application.access_control import (
    can_capture_activity,
    can_edit_structure,
    ensure_planning,
)
from app.scripts.create_admin import provision_admin
from app.shared.application.actor import ActorContext
from app.shared.domain.exceptions import ConflictError, ForbiddenError, ValidationError
from app.shared.infrastructure.db.session import create_database


@pytest.mark.asyncio
async def test_poa_policy_requires_role_and_non_null_area():
    no_area = ActorContext(id=1, roles=frozenset({"capturista_poa"}), area_id=None)
    assert not can_capture_activity(no_area, None)
    assert not can_capture_activity(no_area, 4)
    reviewer = ActorContext(id=2, roles=frozenset({"revisor_poa"}), area_id=4)
    assert not can_capture_activity(reviewer, 4)
    capturer = ActorContext(id=3, roles=frozenset({"capturista_poa"}), area_id=4)
    assert can_capture_activity(capturer, 4)
    assert not can_capture_activity(capturer, 5)
    areas = AsyncMock()
    areas.get_by_id.return_value = Area.create(
        code="PLAN", name="Dirección de Planeación Educativa"
    )
    assert await can_edit_structure(capturer, areas)
    areas.get_by_id.return_value.is_active = False
    assert not await can_edit_structure(capturer, areas)
    with pytest.raises(ForbiddenError):
        ensure_planning(capturer)
    for role in ("admin_sistema", "planeacion_admin"):
        admin = ActorContext(id=4, roles=frozenset({role}), area_id=None)
        assert can_capture_activity(admin, None)
        assert await can_edit_structure(admin, areas)
        ensure_planning(admin)


@pytest.mark.asyncio
async def test_admin_command_requires_persistent_database():
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        await provision_admin(
            Settings(database_url=None),
            email="admin@example.com",
            name="Admin",
            password="password-seguro",
        )


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL no configurada")
@pytest.mark.asyncio
async def test_admin_command_persists_hash_and_rejects_duplicate(monkeypatch):
    settings = Settings(database_url=os.environ["TEST_DATABASE_URL"], database_echo=False)
    email = f"cli-{uuid4().hex}@example.com"
    user_id = await provision_admin(
        settings, email=email, name="Administrador", password="password-seguro"
    )
    engine, factory = create_database(settings)
    try:
        repository = SqlAlchemyUserRepository(factory)
        user = await repository.get_by_id(user_id)
        assert user.roles == frozenset({Role.ADMIN_SISTEMA})
        assert not user.password_setup_required
        assert Argon2PasswordHasher().verify("password-seguro", user.password_hash)
        with pytest.raises(ConflictError):
            await provision_admin(
                settings, email=email, name="No sobrescribir", password="different-password"
            )
        unchanged = await repository.get_by_id(user_id)
        assert unchanged.password_hash == user.password_hash
        assert unchanged.full_name == "Administrador"

        # Un fallo al registrar la bitácora revierte también el alta del usuario.
        from app.modules.audit.infrastructure.sql_repository import SqlAlchemyAuditRepository

        monkeypatch.setattr(
            SqlAlchemyAuditRepository, "append", AsyncMock(side_effect=RuntimeError)
        )
        failed_email = f"rollback-{uuid4().hex}@example.com"
        with pytest.raises(RuntimeError):
            await provision_admin(
                settings, email=failed_email, name="Rollback", password="password-seguro"
            )
        assert await repository.get_by_email(failed_email) is None
    finally:
        await engine.dispose()
