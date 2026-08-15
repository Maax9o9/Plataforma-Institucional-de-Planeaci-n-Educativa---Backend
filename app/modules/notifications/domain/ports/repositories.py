from typing import Protocol

from ..entities import Notification


class NotificationRepository(Protocol):
    async def create(self, notification: Notification) -> Notification: ...
    async def list_for_user(
        self,
        user_id: int,
        unread_only: bool = False,
    ) -> list[Notification]: ...
    async def mark_read(self, notification_id: int, user_id: int) -> None: ...
    async def mark_email_sent(self, notification_id: int) -> None: ...
