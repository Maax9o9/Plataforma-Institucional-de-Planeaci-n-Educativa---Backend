"""Registrar, editar y enviar avances POA."""

from app.shared.application.event_bus import EventBus
from app.shared.domain.exceptions import ConflictError, ForbiddenError, ResourceNotFoundError

from ....evidence_management.domain.value_objects import FlowEntity
from ...domain.entities import PoaAdvance
from ...domain.ports.repositories import EvidenceReader, PoaAdvanceRepository, ReferenceReader
from ..dto import EditAdvanceCommand, RegisterAdvanceCommand, SendAdvanceCommand


def _period_is_open(period) -> bool:
    return period is not None and period.status.value == "abierto"


class RegisterAdvance:
    def __init__(
        self,
        repository: PoaAdvanceRepository,
        activities: ReferenceReader,
        periods: ReferenceReader,
        users: ReferenceReader,
        criteria: ReferenceReader,
        event_bus: EventBus,
    ) -> None:
        self.repository = repository
        self.activities = activities
        self.periods = periods
        self.users = users
        self.criteria = criteria
        self.event_bus = event_bus

    async def execute(self, command: RegisterAdvanceCommand) -> PoaAdvance:
        activity = await self.activities.get_activity(command.activity_id)
        if activity is None:
            raise ResourceNotFoundError("La actividad POA no existe.")
        user = await self.users.get_by_id(command.capturer_id)
        if user is None or not user.is_active:
            raise ForbiddenError("El capturista no existe o esta desactivado.")
        period = await self.periods.get_by_id(command.period_id)
        if not _period_is_open(period):
            raise ConflictError("El periodo POA no esta abierto.")
        for criterion_id in command.criteria_ids:
            criterion = await self.criteria.get_by_id(criterion_id)
            if criterion is None or not criterion.is_active:
                raise ConflictError(
                    f"El criterio SEAES {criterion_id} no existe o esta desactivado."
                )
        if await self.repository.get_by_activity_quarter(command.activity_id, command.quarter):
            raise ConflictError("Ya existe un avance para la actividad y cuatrimestre.")
        item = PoaAdvance.create(
            activity_id=command.activity_id,
            quarter=command.quarter,
            period_id=command.period_id,
            capturer_id=command.capturer_id,
            scheduled=command.scheduled,
            achieved=command.achieved,
            observations=command.observations,
            criteria_ids=command.criteria_ids,
        )
        await self.repository.add(item)
        return item


class EditAdvance:
    def __init__(
        self, repository: PoaAdvanceRepository, periods: ReferenceReader, event_bus: EventBus
    ) -> None:
        self.repository = repository
        self.periods = periods
        self.event_bus = event_bus

    async def execute(self, command: EditAdvanceCommand) -> PoaAdvance:
        item = await self.repository.get_by_id(command.advance_id)
        if item is None:
            raise ResourceNotFoundError("El avance POA no existe.")
        if item.capturer_id != command.actor_id:
            raise ForbiddenError("El usuario no es el capturista del avance.")
        period = await self.periods.get_by_id(item.period_id)
        item.edit(
            period_is_open=_period_is_open(period),
            scheduled=command.scheduled,
            achieved=command.achieved,
            observations=command.observations,
            criteria_ids=command.criteria_ids,
        )
        await self.repository.update(item)
        return item


class SendAdvance:
    def __init__(
        self,
        repository: PoaAdvanceRepository,
        activities: ReferenceReader,
        periods: ReferenceReader,
        evidence: EvidenceReader,
        event_bus: EventBus,
    ) -> None:
        self.repository = repository
        self.activities = activities
        self.periods = periods
        self.evidence = evidence
        self.event_bus = event_bus

    async def execute(self, command: SendAdvanceCommand) -> PoaAdvance:
        item = await self.repository.get_by_id(command.advance_id)
        if item is None:
            raise ResourceNotFoundError("El avance POA no existe.")
        if item.capturer_id != command.actor_id:
            raise ForbiddenError("El usuario no es el capturista del avance.")
        period = await self.periods.get_by_id(item.period_id)
        item.send(
            period_is_open=_period_is_open(period),
            has_evidence=await self.evidence.has_for(FlowEntity.POA_ADVANCE, item.id),
        )
        activity = await self.activities.get_activity(item.activity_id)
        advances = await self.repository.list_by_activity(item.activity_id)
        scheduled_total = sum((advance.scheduled or 0 for advance in advances), 0)
        if activity is not None and activity.annual_goal:
            deviation = abs(scheduled_total - activity.annual_goal) / activity.annual_goal
            if deviation > 0.10:
                item.warnings = [
                    "La suma programada de los cuatrimestres difiere mas de 10% de la meta anual."
                ]
        await self.repository.update(item)
        return item
