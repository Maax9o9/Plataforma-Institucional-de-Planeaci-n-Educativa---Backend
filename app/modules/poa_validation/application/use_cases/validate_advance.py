"""Validar y rechazar avances POA usando cambios_estado compartido."""

from __future__ import annotations

from datetime import UTC, datetime

from app.shared.application.event_bus import EventBus
from app.shared.domain.exceptions import ResourceNotFoundError

from ....indicators_capture.domain.value_objects import CaptureStatus
from ....indicators_validation.domain.entities import StateChange
from ...domain.events import PoaAdvanceRejected, PoaAdvanceValidated
from ...domain.ports.repositories import PoaAdvanceReader
from ..dto import RejectPoaAdvanceCommand, ValidatePoaAdvanceCommand


class ValidatePoaAdvance:
    def __init__(
        self, advances: PoaAdvanceReader, changes, event_bus: EventBus, unit_of_work
    ) -> None:
        self.advances = advances
        self.changes = changes
        self.event_bus = event_bus
        self.unit_of_work = unit_of_work

    async def execute(self, command: ValidatePoaAdvanceCommand):
        async with self.unit_of_work():
            return await self._execute(command)

    async def _execute(self, command: ValidatePoaAdvanceCommand):
        item = await self.advances.get_by_id(command.advance_id)
        if item is None:
            raise ResourceNotFoundError("El avance POA no existe.")
        previous = item.status
        item.validate()
        await self.advances.update(item)
        await self.changes.add(
            StateChange(
                entity_id=item.id,
                from_status=previous,
                to_status=CaptureStatus.VALIDATED,
                user_id=command.user_id,
                comment=None,
                created_at=datetime.now(UTC),
                entity="poa_avance",
            )
        )
        await self.event_bus.publish(
            PoaAdvanceValidated(
                actor_id=command.user_id,
                aggregate_type="poa_advance",
                aggregate_id=item.id,
                action="validated",
                data={
                    "activity_id": item.activity_id,
                    "period_id": item.period_id,
                    "capturer_id": item.capturer_id,
                },
            )
        )
        return item


class RejectPoaAdvance:
    def __init__(
        self, advances: PoaAdvanceReader, changes, event_bus: EventBus, unit_of_work
    ) -> None:
        self.advances = advances
        self.changes = changes
        self.event_bus = event_bus
        self.unit_of_work = unit_of_work

    async def execute(self, command: RejectPoaAdvanceCommand):
        async with self.unit_of_work():
            return await self._execute(command)

    async def _execute(self, command: RejectPoaAdvanceCommand):
        item = await self.advances.get_by_id(command.advance_id)
        if item is None:
            raise ResourceNotFoundError("El avance POA no existe.")
        previous = item.status
        item.reject(command.comment)
        await self.advances.update(item)
        await self.changes.add(
            StateChange(
                entity_id=item.id,
                from_status=previous,
                to_status=CaptureStatus.REJECTED,
                user_id=command.user_id,
                comment=command.comment.strip(),
                created_at=datetime.now(UTC),
                entity="poa_avance",
            )
        )
        await self.event_bus.publish(
            PoaAdvanceRejected(
                actor_id=command.user_id,
                aggregate_type="poa_advance",
                aggregate_id=item.id,
                action="rejected",
                data={
                    "activity_id": item.activity_id,
                    "period_id": item.period_id,
                    "capturer_id": item.capturer_id,
                },
            )
        )
        return item
