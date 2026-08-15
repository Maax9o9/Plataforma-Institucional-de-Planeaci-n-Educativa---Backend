"""Caso de uso invocable por arq/Celery para recordatorios diarios."""

from __future__ import annotations

from datetime import date
from uuid import NAMESPACE_URL, uuid5

from ..domain.entities import Notification


class GenerateReminders:
    def __init__(self, periods, indicators, notifications) -> None:
        self.periods = periods
        self.indicators = indicators
        self.notifications = notifications

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
            for indicator in await self.indicators.list(active_only=True):
                event_id = uuid5(
                    NAMESPACE_URL,
                    f"reminder:{period.id}:{notification_type}:{today.isoformat()}:{indicator.responsible_id}",
                )
                await self.notifications.create(
                    Notification(
                        user_id=indicator.responsible_id,
                        notification_type=notification_type,
                        message=(
                            f"El periodo {period.name} vence el {period.ends_on.isoformat()}. "
                            "Revisa tus pendientes."
                        ),
                        entity="periodo",
                        entity_id=period.id,
                        source_event_id=event_id,
                    )
                )
                created += 1
        return created
