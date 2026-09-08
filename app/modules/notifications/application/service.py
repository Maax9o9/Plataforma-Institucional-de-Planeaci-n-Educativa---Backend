"""Suscriptores de eventos y entrega segura de correo."""

from __future__ import annotations

import asyncio
import logging
from html import escape

from app.shared.application.event_bus import EventBus
from app.shared.application.ports.email_sender import EmailSender
from app.shared.domain.domain_event import DomainEvent
from app.shared.infrastructure.db.unit_of_work import run_after_commit

from ..domain.entities import Notification
from ..domain.ports.repositories import NotificationRepository

logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(
        self,
        repository: NotificationRepository,
        user_repository,
        email_sender: EmailSender,
        indicator_repository=None,
        poa_recipients=None,
    ) -> None:
        self.repository = repository
        self.user_repository = user_repository
        self.email_sender = email_sender
        self.indicator_repository = indicator_repository
        self.poa_recipients = poa_recipients
        self._delivery_tasks: set[asyncio.Task] = set()

    def register(self, event_bus: EventBus) -> None:
        event_bus.subscribe(DomainEvent, self.handle_event)

    async def handle_event(self, event: DomainEvent) -> None:
        if event.aggregate_type == "poa_form_activity" and event.data.get("assigned_area_id"):
            if self.poa_recipients is not None:
                for user_id in await self.poa_recipients.for_assignment(
                    event.data["assigned_area_id"]
                ):
                    await self.notify_user(
                        user_id=user_id,
                        notification_type="poa_actividad_asignada",
                        message=(
                            f"Se asignó a tu área la actividad {event.data.get('activity_key')} "
                            f"de la cédula {event.data.get('form_id')}. "
                            "Revisa sus fechas y captura el seguimiento con evidencia."
                        ),
                        entity="poa_form_activity",
                        entity_id=event.aggregate_id,
                        source_event_id=event.event_id,
                    )
            return
        event_name = event.__class__.__name__
        notification_type = self._type_for(event_name)
        recipients = await self._recipients_for(event)
        for user_id in recipients:
            await self.notify_user(
                user_id=user_id,
                notification_type=notification_type,
                message=self._message(event),
                entity="periodo" if event.aggregate_type == "period" else event.aggregate_type,
                entity_id=event.aggregate_id,
                source_event_id=event.event_id,
            )

    async def notify_user(
        self,
        *,
        user_id: int,
        notification_type: str,
        message: str,
        entity: str | None,
        entity_id: int | None,
        source_event_id,
    ) -> Notification:
        """Persiste y entrega una notificacion sin duplicar correos idempotentes."""

        notification = await self.repository.create(
            Notification(
                user_id=user_id,
                notification_type=notification_type,
                message=message,
                entity=entity,
                entity_id=entity_id,
                source_event_id=source_event_id,
            )
        )
        user = await self.user_repository.get_by_id(user_id)
        if (
            user is not None
            and user.is_active
            and user.notify_email
            and not notification.sent_by_email
        ):

            async def send_after_commit(notification=notification, email=user.email.value):
                task = asyncio.create_task(self._send_email(notification, email))
                self._delivery_tasks.add(task)
                task.add_done_callback(self._delivery_tasks.discard)

            await run_after_commit(send_after_commit)
            await asyncio.sleep(0)
        return notification

    async def _send_email(self, notification: Notification, recipient: str) -> None:
        try:
            if not await self.repository.claim_email(notification.id):
                return
            async with asyncio.timeout(60):
                await self.email_sender.send(
                    recipient,
                    f"Plataforma de Planeacion: {notification.notification_type}",
                    f"<p>{escape(notification.message)}</p>",
                    notification.message,
                )
            await self.repository.mark_email_sent(notification.id)
        except Exception:
            logger.exception("No se pudo entregar la notificacion por correo")
            # La reserva vence incluso si tampoco es posible contactar la BD para liberarla.
            try:
                await self.repository.release_email(notification.id)
            except Exception:
                logger.exception("No se pudo liberar la reserva del correo")

    async def retry_pending(self) -> None:
        after_id = 0
        while batch := await self.repository.pending_email(after_id=after_id):
            for notification in batch:
                user = await self.user_repository.get_by_id(notification.user_id)
                if user is not None and user.is_active and user.notify_email:
                    await self._send_email(notification, user.email.value)
            # Usuarios sin correo y fallos antiguos no bloquean los siguientes lotes.
            after_id = batch[-1].id

    async def close(self) -> None:
        tasks = tuple(self._delivery_tasks)
        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=10)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    async def _recipients_for(self, event: DomainEvent) -> set[int]:
        if event.data.get("capturer_id"):
            return {int(event.data["capturer_id"])}
        if event.data.get("recipient_id"):
            return {int(event.data["recipient_id"])}
        if event.__class__.__name__ == "PeriodOpened" and self.indicator_repository:
            if event.data.get("type") == "poa":
                # El scheduler avisa según las fechas y sólo a quienes tienen pendientes.
                return set()
            recipients: set[int] = set()
            for indicator in await self.indicator_repository.list(active_only=True):
                if event.data.get("periodicity") in {None, indicator.periodicity.value}:
                    recipients.add(indicator.responsible_id)
            return recipients
        return set()

    @staticmethod
    def _type_for(event_name: str) -> str:
        if "Rejected" in event_name or "Rechaz" in event_name:
            return "rechazo"
        if event_name == "PeriodOpened":
            return "apertura_periodo"
        return "validacion"

    @staticmethod
    def _message(event: DomainEvent) -> str:
        if event.action == "rejected":
            return (
                "Tu registro fue rechazado. Revisa el comentario y realiza "
                "las correcciones necesarias."
            )
        if event.action == "opened":
            return "Se abrio un nuevo periodo de captura."
        return "Tu registro cambio de estado y requiere tu atencion."
