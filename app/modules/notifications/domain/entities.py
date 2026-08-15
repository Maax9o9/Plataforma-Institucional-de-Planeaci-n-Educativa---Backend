"""Entidad de notificaciones internas."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.shared.domain.base_entity import BaseEntity


@dataclass(kw_only=True)
class Notification(BaseEntity):
    user_id: int
    notification_type: str
    message: str
    entity: str | None = None
    entity_id: int | None = None
    read: bool = False
    sent_by_email: bool = False
    source_event_id: UUID | None = None
    created_at: datetime | None = None
