"""Caso de uso invocable por arq/Celery para recordatorios diarios."""

from __future__ import annotations

from datetime import date
from uuid import NAMESPACE_URL, uuid5

from ..domain.entities import Notification


class GenerateReminders:
    def __init__(
        self,
        periods,
        indicators,
        notifications,
        poa_recipients=None,
        notification_service=None,
    ) -> None:
        self.periods = periods
        self.indicators = indicators
        self.notifications = notifications
        self.poa_recipients = poa_recipients
        self.notification_service = notification_service

    async def _responsible_ids(self, period) -> set[int]:
        if period.period_type.value == "poa":
            return (
                await self.poa_recipients.for_period(period.id)
                if self.poa_recipients is not None else set()
            )
        return {
            indicator.responsible_id
            for indicator in await self.indicators.list(active_only=True)
            if period.periodicity is None or indicator.periodicity == period.periodicity
        }

    async def execute(self, today: date | None = None) -> int:
        today = today or date.today()
        created = 0
        for period in await self.periods.list():
            if period.status.value != "abierto":
                continue
            days_left = (period.ends_on - today).days
            if days_left not in {5, 3, 2, 1}:
                continue
            notification_type = f"recordatorio_{days_left}d"
            message = (
                f"El periodo {period.name} vence el {period.ends_on.isoformat()}. "
                "Revisa tus pendientes."
            )
            for responsible_id in await self._responsible_ids(period):
                event_id = uuid5(
                    NAMESPACE_URL,
                    f"reminder:{period.id}:{notification_type}:{today.isoformat()}:{responsible_id}",
                )
                if self.notification_service is not None:
                    await self.notification_service.notify_user(
                        user_id=responsible_id,
                        notification_type=notification_type,
                        message=message,
                        entity="periodo",
                        entity_id=period.id,
                        source_event_id=event_id,
                    )
                else:
                    await self.notifications.create(
                        Notification(
                            user_id=responsible_id,
                            notification_type=notification_type,
                            message=message,
                            entity="periodo",
                            entity_id=period.id,
                            source_event_id=event_id,
                        )
                    )
                created += 1
        return created
