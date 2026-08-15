"""Reapertura formal con motivo obligatorio."""

from app.shared.application.event_bus import EventBus
from app.shared.domain.exceptions import ResourceNotFoundError

from ...domain.events import PeriodReopened
from ...domain.ports.repository import PeriodRepository
from ..dto import ReopenPeriodCommand


class ReopenPeriod:
    def __init__(
        self,
        repository: PeriodRepository,
        event_bus: EventBus,
        poa_reopener=None,
    ) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.poa_reopener = poa_reopener

    async def execute(self, command: ReopenPeriodCommand):
        period = await self.repository.get_by_id(command.period_id)
        if period is None:
            raise ResourceNotFoundError("El periodo no existe.")
        period.reopen(command.reason, command.actor_id)
        await self.repository.update(period)
        if period.period_type.value == "poa" and self.poa_reopener is not None:
            await self.poa_reopener.reset_validated_for_period(period.id, command.actor_id)
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
