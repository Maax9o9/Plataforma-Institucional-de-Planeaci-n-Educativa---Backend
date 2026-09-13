"""Comandos de aplicación para la cédula institucional POA."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.shared.application.actor import ActorContext

from ..domain.cedula_entities import PoaSignatory


@dataclass(frozen=True)
class PoaQuarterRangeInput:
    quarter: int
    starts_on: date
    ends_on: date


@dataclass(frozen=True)
class CreatePoaFormCommand:
    exercise_id: int
    strategy_key: str
    responsible_area_id: int
    scope_and_socioeconomic_effect: str | None
    quarters: tuple[PoaQuarterRangeInput, ...]
    actor: ActorContext
    strategy_type: str | None = None
    signatories: tuple[PoaSignatory, ...] = ()


@dataclass(frozen=True)
class UpdatePoaFormCommand:
    form_id: int
    strategy_key: str | None
    responsible_area_id: int | None
    scope_and_socioeconomic_effect: str | None
    actor: ActorContext
    strategy_type: str | None = None
    signatories: tuple[PoaSignatory, ...] | None = None


@dataclass(frozen=True)
class DeletePoaFormCommand:
    form_id: int
    actor: ActorContext


@dataclass(frozen=True)
class AddPoaFormIndicatorCommand:
    form_id: int
    indicator_key: str
    institutional_goal: Decimal | None
    baseline_year: int | None
    baseline_value: Decimal | None
    current_percentage: Decimal | None
    target_value: Decimal | None
    target_percentage: Decimal | None
    actor: ActorContext


@dataclass(frozen=True)
class UpdatePoaFormIndicatorCommand:
    form_indicator_id: int
    institutional_goal: Decimal | None
    baseline_year: int | None
    baseline_value: Decimal | None
    current_percentage: Decimal | None
    target_value: Decimal | None
    target_percentage: Decimal | None
    actor: ActorContext


@dataclass(frozen=True)
class DeletePoaFormIndicatorCommand:
    form_indicator_id: int
    actor: ActorContext


@dataclass(frozen=True)
class CapturePoaIndicatorTotalCommand:
    form_indicator_id: int
    period_id: int
    total_achieved: Decimal
    achieved_percentage: Decimal | None
    actor: ActorContext


@dataclass(frozen=True)
class AddPoaFormActivityCommand:
    form_id: int
    activity_key: str
    unit: str
    annual_goal: Decimal
    executing_area_id: int | None
    observations: str | None
    actor: ActorContext


@dataclass(frozen=True)
class UpdatePoaFormActivityCommand:
    form_activity_id: int
    unit: str | None
    annual_goal: Decimal | None
    executing_area_id: int | None
    observations: str | None
    upe_description: str | None
    actor: ActorContext


@dataclass(frozen=True)
class DeletePoaFormActivityCommand:
    form_activity_id: int
    actor: ActorContext


@dataclass(frozen=True)
class AssignPoaActivityCriteriaCommand:
    form_activity_id: int
    criteria_seaes_ids: tuple[int, ...]
    actor: ActorContext


@dataclass(frozen=True)
class RecordPoaFollowUpCommand:
    form_activity_id: int
    quarter: int
    period_id: int
    scheduled: Decimal
    achieved: Decimal | None
    deviation_justification: str | None
    progress: str | None
    scope: str | None
    actor: ActorContext


@dataclass(frozen=True)
class UpdatePoaFollowUpJustificationCommand:
    follow_up_id: int
    justification: str
    actor: ActorContext


@dataclass(frozen=True)
class IssuePoaFormCommand:
    form_id: int
    quarter: int
    period_id: int
    actor: ActorContext
