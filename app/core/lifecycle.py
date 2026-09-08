"""Lifecycle de recursos compartidos de la aplicacion."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.modules.notifications.application.reminders import GenerateReminders

logger = logging.getLogger(__name__)


async def _run_reminder_scheduler(app: FastAPI) -> None:
    while True:
        try:
            total = await GenerateReminders(
                app.state.period_repository,
                app.state.indicator_repository,
                app.state.notification_repository,
                app.state.poa_period_recipients,
                app.state.notification_service,
            ).execute()
            if total:
                logger.info("Recordatorios periodicos procesados: %s", total)
            await app.state.notification_service.retry_pending()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Fallo la generacion automatica de recordatorios")
        await asyncio.sleep(app.state.settings.reminder_check_interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = app.state.settings
    await app.state.poa_form_repository.ensure_catalogs()
    if settings.bootstrap_admin_email or settings.bootstrap_admin_password:
        logger.warning(
            "BOOTSTRAP_ADMIN_* ya no crea usuarios. Usa python -m app.scripts.create_admin."
        )
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
        await app.state.notification_service.close()
        if app.state.db_engine is not None:
            await app.state.db_engine.dispose()
