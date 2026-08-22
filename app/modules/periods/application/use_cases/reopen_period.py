"""Reapertura formal con motivo obligatorio."""

from datetime import UTC, datetime

from app.shared.application.event_bus import EventBus
from app.shared.domain.exceptions import ResourceNotFoundError

from ....indicators_capture.domain.value_objects import CaptureStatus
from ....indicators_validation.domain.entities import StateChange
from ...domain.events import PeriodReopened
from ...domain.ports.repository import PeriodRepository
from ..dto import ReopenPeriodCommand


class ReopenPeriod:
    def __init__(
        self,
        repository: PeriodRepository,
        event_bus: EventBus,
        capture_reopener=None,
        poa_reopener=None,
        state_changes=None,
        unit_of_work=None,
    ) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.capture_reopener = capture_reopener
        self.poa_reopener = poa_reopener
        self.state_changes = state_changes
        self.unit_of_work = unit_of_work

    async def execute(self, command: ReopenPeriodCommand):
        if self.unit_of_work is None:
            return await self._execute(command)
        async with self.unit_of_work():
            return await self._execute(command)

    async def _execute(self, command: ReopenPeriodCommand):
        period = await self.repository.get_by_id(command.period_id)
        if period is None:
            raise ResourceNotFoundError("El periodo no existe.")
        period.reopen(command.reason, command.actor_id)
        await self.repository.update(period)
        reset_ids: list[int] = []
        entity = "captura"
        if period.period_type.value == "indicadores" and self.capture_reopener is not None:
            reset_ids = await self.capture_reopener.reset_validated_for_period(
                period.id, command.actor_id
            )
        if period.period_type.value == "poa" and self.poa_reopener is not None:
            entity = "poa_avance"
            reset_ids = await self.poa_reopener.reset_validated_for_period(
                period.id, command.actor_id
            )
        if self.state_changes is not None:
            for entity_id in reset_ids:
                await self.state_changes.add(
                    StateChange(
                        entity=entity,
                        entity_id=entity_id,
                        from_status=CaptureStatus.VALIDATED,
                        to_status=CaptureStatus.DRAFT,
                        user_id=command.actor_id,
                        comment=f"Reapertura: {command.reason.strip()}",
                        created_at=datetime.now(UTC),
                    )
                )
        await self.event_bus.publish(
            PeriodReopened(
                actor_id=command.actor_id,
                aggregate_type="period",
                aggregate_id=period.id,
                action="reopened",
                data={"name": period.name, "reason": command.reason.strip()},
            )
        )
        return period
