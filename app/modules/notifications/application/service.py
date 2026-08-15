"""Suscriptores de eventos y entrega segura de correo."""

from __future__ import annotations

import asyncio
import logging

from app.shared.application.event_bus import EventBus
from app.shared.application.ports.email_sender import EmailSender
from app.shared.domain.domain_event import DomainEvent

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
    ) -> None:
        self.repository = repository
        self.user_repository = user_repository
        self.email_sender = email_sender
        self.indicator_repository = indicator_repository

    def register(self, event_bus: EventBus) -> None:
        event_bus.subscribe(DomainEvent, self.handle_event)

    async def handle_event(self, event: DomainEvent) -> None:
        event_name = event.__class__.__name__
        notification_type = self._type_for(event_name)
        recipients = await self._recipients_for(event)
        scheduled_email = False
        for user_id in recipients:
            notification = await self.repository.create(
                Notification(
                    user_id=user_id,
                    notification_type=notification_type,
                    message=self._message(event),
                    entity=event.aggregate_type,
                    entity_id=event.aggregate_id,
                    source_event_id=event.event_id,
                )
            )
            user = await self.user_repository.get_by_id(user_id)
            if user is not None and user.notify_email:
                asyncio.create_task(self._send_email(notification, user.email.value))
                scheduled_email = True
        if scheduled_email:
            await asyncio.sleep(0)

    async def _send_email(self, notification: Notification, recipient: str) -> None:
        try:
            await self.email_sender.send(
                recipient,
                f"Plataforma de Planeacion: {notification.notification_type}",
                f"<p>{notification.message}</p>",
                notification.message,
            )
            await self.repository.mark_email_sent(notification.id)
        except Exception:
            logger.exception("No se pudo entregar la notificacion por correo")

    async def _recipients_for(self, event: DomainEvent) -> set[int]:
        if event.data.get("capturer_id"):
            return {int(event.data["capturer_id"])}
        if event.data.get("recipient_id"):
            return {int(event.data["recipient_id"])}
        if event.__class__.__name__ == "PeriodOpened" and self.indicator_repository:
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
