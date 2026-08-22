"""DTOs de planeacion POA."""

from dataclasses import dataclass
from decimal import Decimal

from app.shared.application.actor import ActorContext


@dataclass(frozen=True)
class CreateExerciseCommand:
    year: int
    actor_id: int


@dataclass(frozen=True)
class CreateProcessCommand:
    exercise_id: int
    name: str
    area_id: int
    actor_id: int


@dataclass(frozen=True)
class CreateObjectiveCommand:
    process_id: int
    poa_indicator: str | None
    objective: str
    actor_id: int


@dataclass(frozen=True)
class CreateActivityCommand:
    objective_id: int
    description: str
    unit: str
    annual_goal: Decimal
    observations: str | None
    responsible_id: int
    actor: ActorContext


@dataclass(frozen=True)
class UpdateActivityCommand:
    activity_id: int
    description: str | None
    unit: str | None
    annual_goal: Decimal | None
    observations: str | None
    responsible_id: int | None
    actor: ActorContext
