"""Lifecycle de recursos compartidos de la aplicacion."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.modules.identity_access.application.dto import RegisterUserCommand
from app.modules.identity_access.application.use_cases.create_user import CreateUser
from app.modules.identity_access.domain.value_objects import Role

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = app.state.settings
    if settings.bootstrap_admin_email and settings.bootstrap_admin_password:
        if await app.state.user_repository.get_by_email(settings.bootstrap_admin_email) is None:
            await CreateUser(
                repository=app.state.user_repository,
                password_hasher=app.state.password_hasher,
                event_bus=app.state.event_bus,
            ).execute(
                RegisterUserCommand(
                    email=settings.bootstrap_admin_email,
                    full_name="Administrador inicial",
                    password=settings.bootstrap_admin_password,
                    roles={Role.ADMIN_SISTEMA},
                    area_id=None,
                )
            )
            logger.info("Usuario administrador inicial creado")
    elif settings.environment == "development":
        logger.info("No se configuro usuario bootstrap; la autenticacion inicia sin usuarios")
    try:
        yield
    finally:
        if app.state.db_engine is not None:
            await app.state.db_engine.dispose()
