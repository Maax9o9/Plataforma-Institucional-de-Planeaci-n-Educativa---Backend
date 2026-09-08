"""Repositorios de notificaciones."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import count

from ..domain.entities import Notification


class InMemoryNotificationRepository:
    def __init__(self) -> None:
        self._items: dict[int, Notification] = {}
        self._next_id = count(1)
        self._email_leases: dict[int, datetime] = {}

    async def create(self, notification: Notification) -> Notification:
        for item in self._items.values():
            if (
                item.user_id == notification.user_id
                and item.notification_type == notification.notification_type
                and item.source_event_id == notification.source_event_id
                and notification.source_event_id is not None
            ):
                return item
        notification.id = next(self._next_id)
        notification.created_at = notification.created_at or datetime.now(UTC)
        self._items[notification.id] = notification
        return notification

    async def list_for_user(self, user_id: int, unread_only: bool = False) -> list[Notification]:
        items = [item for item in self._items.values() if item.user_id == user_id]
        if unread_only:
            items = [item for item in items if not item.read]
        return sorted(items, key=lambda item: item.id, reverse=True)

    async def mark_read(self, notification_id: int, user_id: int) -> None:
        item = self._items.get(notification_id)
        if item and item.user_id == user_id:
            item.read = True

    async def mark_email_sent(self, notification_id: int) -> None:
        if notification_id in self._items:
            self._items[notification_id].sent_by_email = True
        self._email_leases.pop(notification_id, None)

    async def pending_email(self, limit: int = 100, after_id: int = 0) -> list[Notification]:
        now = datetime.now(UTC)
        return [
            item
            for item in self._items.values()
            if item.id > after_id
            and not item.sent_by_email
            and self._email_leases.get(item.id, now) <= now
        ][:limit]

    async def claim_email(self, notification_id: int) -> bool:
        now = datetime.now(UTC)
        item = self._items.get(notification_id)
        if item is None or item.sent_by_email or self._email_leases.get(item.id, now) > now:
            return False
        self._email_leases[item.id] = now + timedelta(minutes=5)
        return True

    async def release_email(self, notification_id: int) -> None:
        self._email_leases.pop(notification_id, None)
