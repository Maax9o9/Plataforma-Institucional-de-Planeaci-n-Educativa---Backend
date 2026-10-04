"""Ciclo de vida del ejercicio anual del POA.

Planeación arma el ejercicio y lo manda a Rectoría; Rectoría lo aprueba o lo
devuelve con un motivo; al terminar el año, Planeación lo cierra. A diferencia
del seguimiento cuatrimestral (EP-08, `review_follow_up.py`), un ejercicio
aprobado no se queda quieto: entra en vigor y sigue vivo hasta que se cierra.

El registro en `cambios_estado` y la publicación al bus de eventos siguen el
mismo patrón que `review_follow_up.py`, para que el historial se lea igual sin
importar si la entidad es un seguimiento o un ejercicio completo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.modules.indicators_validation.domain.entities import StateChange
from app.shared.application.actor import ActorContext
from app.shared.application.event_bus import EventBus
from app.shared.domain.domain_event import DomainEvent
from app.shared.domain.exceptions import ForbiddenError, ResourceNotFoundError

from ...domain.entities import PoaExercise
from ...domain.ports.cedula_repository import PoaFormRepository
from ...domain.ports.repositories import PoaRepository
from ...domain.value_objects import PoaExerciseStatus
from ..access_control import can_approve_exercise

#: Entidad con la que el ejercicio se registra en `cambios_estado`.
ENTITY = "poa_ejercicio"


@dataclass(frozen=True)
class ExerciseActionCommand:
    exercise_id: int
    actor: ActorContext
    comment: str | None = None


class _BaseExerciseAction:
    def __init__(
        self,
        repository: PoaRepository,
        form_repository: PoaFormRepository,
        state_changes,
        event_bus: EventBus,
    ) -> None:
        self.repository = repository
        self.form_repository = form_repository
        self.state_changes = state_changes
        self.event_bus = event_bus

    async def _load(self, exercise_id: int) -> PoaExercise:
        item = await self.repository.get_exercise(exercise_id)
        if item is None:
            raise ResourceNotFoundError("El ejercicio POA no existe.")
        return item

    async def _record(
        self,
        item: PoaExercise,
        previous: PoaExerciseStatus,
        actor: ActorContext,
        comment: str | None,
    ) -> None:
        await self.repository.update_exercise(item)
        await self.state_changes.add(
            StateChange(
                entity=ENTITY,
                entity_id=item.id,
                from_status=previous,
                to_status=item.status,
                user_id=actor.id,
                comment=comment,
                created_at=datetime.now(UTC),
            )
        )
        await self.event_bus.publish(
            DomainEvent(
                actor_id=actor.id,
                aggregate_type="poa_exercise",
                aggregate_id=item.id,
                action=item.status.value,
                data={"year": item.year, "from_status": previous.value},
            )
        )


class SendExercise(_BaseExerciseAction):
    """Planeación manda el ejercicio a Rectoría para su aprobación."""

    async def execute(self, command: ExerciseActionCommand) -> PoaExercise:
        item = await self._load(command.exercise_id)
        forms = await self.form_repository.list_forms(exercise_id=item.id)

        previous = item.status
        item.send(has_forms=bool(forms))
        await self._record(item, previous, command.actor, None)
        return item


class ApproveExercise(_BaseExerciseAction):
    """Rectoría aprueba el ejercicio: entra en vigor."""

    async def execute(self, command: ExerciseActionCommand) -> PoaExercise:
        if not can_approve_exercise(command.actor):
            raise ForbiddenError("Tu rol no permite aprobar el ejercicio POA.")
        item = await self._load(command.exercise_id)

        previous = item.status
        item.approve()
        await self._record(item, previous, command.actor, None)
        return item


class RejectExercise(_BaseExerciseAction):
    """Rectoría devuelve el ejercicio con un motivo visible para Planeación."""

    async def execute(self, command: ExerciseActionCommand) -> PoaExercise:
        if not can_approve_exercise(command.actor):
            raise ForbiddenError("Tu rol no permite devolver el ejercicio POA.")
        item = await self._load(command.exercise_id)

        previous = item.status
        item.reject(command.comment or "")
        await self._record(item, previous, command.actor, item.review_comment)
        return item


class CloseExercise(_BaseExerciseAction):
    """Planeación cierra el ejercicio vigente al terminar el año."""

    async def execute(self, command: ExerciseActionCommand) -> PoaExercise:
        item = await self._load(command.exercise_id)

        previous = item.status
        item.close()
        await self._record(item, previous, command.actor, None)
        return item
