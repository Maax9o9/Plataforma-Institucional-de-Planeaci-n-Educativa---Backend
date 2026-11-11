"""Validar, rechazar y consultar historial de capturas."""

from __future__ import annotations

from datetime import UTC, datetime

from app.shared.application.event_bus import EventBus
from app.shared.domain.exceptions import ResourceNotFoundError

from ....indicators_capture.domain.entities import Capture
from ....indicators_capture.domain.value_objects import CaptureStatus
from ...domain.entities import StateChange
from ...domain.events import CaptureRejected, CaptureValidated
from ...domain.ports.repositories import CaptureReader, StateChangeRepository
from ..dto import RejectCaptureCommand, ValidateCaptureCommand


class ValidateCapture:
    def __init__(
        self,
        captures: CaptureReader,
        changes: StateChangeRepository,
        event_bus: EventBus,
        unit_of_work,
    ) -> None:
        self.captures = captures
        self.changes = changes
        self.event_bus = event_bus
        self.unit_of_work = unit_of_work

    async def execute(self, command: ValidateCaptureCommand) -> Capture:
        async with self.unit_of_work():
            return await self._execute(command)

    async def _execute(self, command: ValidateCaptureCommand) -> Capture:
        capture = await self.captures.get_by_id(command.capture_id)
        if capture is None:
            raise ResourceNotFoundError("La captura no existe.")
        previous = capture.status
        capture.validate()
        await self.captures.update(capture)
        await self.changes.add(
            StateChange(
                entity_id=capture.id,
                from_status=previous,
                to_status=CaptureStatus.VALIDATED,
                user_id=command.user_id,
                comment=None,
                created_at=datetime.now(UTC),
            )
        )
        await self.event_bus.publish(
            CaptureValidated(
                actor_id=command.user_id,
                aggregate_type="capture",
                aggregate_id=capture.id,
                action="validated",
                data={
                    "capture_id": capture.id,
                    "indicator_id": capture.indicator_id,
                    "period_id": capture.period_id,
                    "capturer_id": capture.capturer_id,
                },
            )
        )
        return await self.captures.get_by_id(capture.id) or capture


class RejectCapture:
    def __init__(
        self,
        captures: CaptureReader,
        changes: StateChangeRepository,
        event_bus: EventBus,
        unit_of_work,
    ) -> None:
        self.captures = captures
        self.changes = changes
        self.event_bus = event_bus
        self.unit_of_work = unit_of_work

    async def execute(self, command: RejectCaptureCommand) -> Capture:
        async with self.unit_of_work():
            return await self._execute(command)

    async def _execute(self, command: RejectCaptureCommand) -> Capture:
        capture = await self.captures.get_by_id(command.capture_id)
        if capture is None:
            raise ResourceNotFoundError("La captura no existe.")
        previous = capture.status
        capture.reject(command.comment)
        await self.captures.update(capture)
        await self.changes.add(
            StateChange(
                entity_id=capture.id,
                from_status=previous,
                to_status=CaptureStatus.REJECTED,
                user_id=command.user_id,
                comment=command.comment.strip(),
                created_at=datetime.now(UTC),
            )
        )
        await self.event_bus.publish(
            CaptureRejected(
                actor_id=command.user_id,
                aggregate_type="capture",
                aggregate_id=capture.id,
                action="rejected",
                data={
                    "capture_id": capture.id,
                    "indicator_id": capture.indicator_id,
                    "period_id": capture.period_id,
                    "capturer_id": capture.capturer_id,
                },
            )
        )
        return capture
