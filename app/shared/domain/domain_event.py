"""Eventos de dominio usados para desacoplar auditoria y notificaciones."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from .base_entity import utc_now


@dataclass(frozen=True)
class DomainEvent:
    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=utc_now)
    actor_id: int | None = None
    aggregate_type: str = ""
    aggregate_id: int | None = None
    action: str = ""
    data: dict[str, Any] = field(default_factory=dict)
