"""DTOs internos de capturas."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class RegisterCaptureCommand:
    indicator_id: int
    period_id: int
    capturer_id: int
    result: Decimal | None
    source_data: str | None
    activity: str | None
    observations: str | None


@dataclass(frozen=True)
class EditCaptureCommand:
    capture_id: int
    actor_id: int
    result: Decimal | None
    source_data: str | None
    activity: str | None
    observations: str | None


@dataclass(frozen=True)
class SendCaptureCommand:
    capture_id: int
    actor_id: int
