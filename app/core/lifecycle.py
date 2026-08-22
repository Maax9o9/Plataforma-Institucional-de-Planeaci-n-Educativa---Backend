"""Lifecycle de recursos compartidos de la aplicacion."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.modules.identity_access.application.dto import RegisterUserCommand
from app.modules.identity_access.application.use_cases.create_user import CreateUser
from app.modules.identity_access.domain.value_objects import Role
from app.modules.notifications.application.reminders import GenerateReminders

logger = logging.getLogger(__name__)


async def _run_reminder_scheduler(app: FastAPI) -> None:
    while True:
        try:
            total = await GenerateReminders(
                app.state.period_repository,
                app.state.indicator_repository,
                app.state.notification_repository,
                app.state.poa_repository,
                app.state.notification_service,
            ).execute()
            if total:
                logger.info("Recordatorios periodicos procesados: %s", total)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Fallo la generacion automatica de recordatorios")
        await asyncio.sleep(app.state.settings.reminder_check_interval_seconds)


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
    reminder_task = None
    if settings.environment != "testing":
        reminder_task = asyncio.create_task(_run_reminder_scheduler(app))
    try:
        yield
    finally:
        if reminder_task is not None:
            reminder_task.cancel()
            with suppress(asyncio.CancelledError):
                await reminder_task
        if app.state.db_engine is not None:
            await app.state.db_engine.dispose()
