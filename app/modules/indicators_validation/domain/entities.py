"""Registro de transiciones de estado de capturas."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.shared.domain.base_entity import BaseEntity

from ...indicators_capture.domain.value_objects import CaptureStatus


@dataclass(kw_only=True)
class StateChange(BaseEntity):
    entity_id: int
    from_status: CaptureStatus | None
    to_status: CaptureStatus
    user_id: int
    comment: str | None
    created_at: datetime
    entity: str = "captura"
