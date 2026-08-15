"""DTOs del seguimiento POA."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class RegisterAdvanceCommand:
    activity_id: int
    quarter: int
    period_id: int
    capturer_id: int
    scheduled: Decimal | None
    achieved: Decimal | None
    observations: str | None
    criteria_ids: set[int]


@dataclass(frozen=True)
class EditAdvanceCommand:
    advance_id: int
    actor_id: int
    scheduled: Decimal | None
    achieved: Decimal | None
    observations: str | None
    criteria_ids: set[int] | None


@dataclass(frozen=True)
class SendAdvanceCommand:
    advance_id: int
    actor_id: int
