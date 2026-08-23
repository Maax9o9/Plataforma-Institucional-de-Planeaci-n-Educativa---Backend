"""Proyecciones de lectura para la bandeja de capturas."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True)
class CaptureListRow:
    id: int
    indicator_id: int
    indicator_key: str
    indicator_name: str
    indicator_unit: str
    period_id: int
    period_label: str
    period_status: str
    period_deadline: date
    area_id: int
    area_code: str
    area_name: str
    area_color: str | None
    capturer_id: int
    capturer_name: str
    capturer_email: str
    result: Decimal | None
    goal: Decimal | None
    progress_percentage: Decimal | None
    semaphore: str | None
    status: str
    evidence_total: int
    updated_at: datetime
