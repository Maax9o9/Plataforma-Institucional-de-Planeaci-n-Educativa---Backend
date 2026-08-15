"""DTOs internos de periodos."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..domain.value_objects import Periodicity, PeriodType


@dataclass(frozen=True)
class CreatePeriodCommand:
    name: str
    starts_on: date
    ends_on: date
    period_type: PeriodType
    periodicity: Periodicity | None
    year: int
    actor_id: int | None


@dataclass(frozen=True)
class ChangePeriodCommand:
    period_id: int
    actor_id: int


@dataclass(frozen=True)
class ReopenPeriodCommand:
    period_id: int
    reason: str
    actor_id: int
