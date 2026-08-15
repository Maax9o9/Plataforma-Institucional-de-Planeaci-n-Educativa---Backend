"""DTOs internos de los casos de uso de indicadores."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..domain.value_objects import IndicatorPeriodicity


@dataclass(frozen=True)
class RegisterIndicatorCommand:
    key: str
    name: str
    calculation_method: str
    unit: str
    area_id: int
    responsible_id: int
    periodicity: IndicatorPeriodicity
    definition: str | None
    dimension: str | None
    verification_document: str | None
    information_source: str | None
    methodological_notes: str | None
    indicator_type_id: int | None
    instrument_ids: set[int]
    green_threshold: int | None
    yellow_threshold: int | None
    actor_id: int


@dataclass(frozen=True)
class UpdateIndicatorCommand:
    indicator_id: int
    actor_id: int
    changes: dict


@dataclass(frozen=True)
class ChangeIndicatorStatusCommand:
    indicator_id: int
    actor_id: int


@dataclass(frozen=True)
class CreateBaselineCommand:
    indicator_id: int
    year: int
    period: str | None
    value: Decimal
    actor_id: int


@dataclass(frozen=True)
class CreateGoalCommand:
    indicator_id: int
    period_id: int
    value: Decimal
    actor_id: int


@dataclass(frozen=True)
class ChangePeriodicityCommand:
    indicator_id: int
    periodicity: IndicatorPeriodicity
    actor_id: int
