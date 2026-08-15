"""Casos de uso de abrir y cerrar periodos."""

from app.shared.application.event_bus import EventBus
from app.shared.domain.exceptions import ResourceNotFoundError

from ...domain.entities import Period
from ...domain.events import PeriodClosed, PeriodOpened
from ...domain.ports.repository import PeriodRepository
from ..dto import ChangePeriodCommand


class OpenPeriod:
    def __init__(self, repository: PeriodRepository, event_bus: EventBus) -> None:
        self.repository = repository
        self.event_bus = event_bus

    async def execute(self, command: ChangePeriodCommand) -> Period:
        period = await self.repository.get_by_id(command.period_id)
        if period is None:
            raise ResourceNotFoundError("El periodo no existe.")
        period.open()
        await self.repository.update(period)
        await self.event_bus.publish(
            PeriodOpened(
                actor_id=command.actor_id,
                aggregate_type="period",
                aggregate_id=period.id,
                action="opened",
                data={
                    "name": period.name,
                    "type": period.period_type.value,
                    "periodicity": period.periodicity.value if period.periodicity else None,
                    "fecha_limite": period.ends_on.isoformat(),
                },
            )
        )
        return period


class ClosePeriod:
    def __init__(self, repository: PeriodRepository, event_bus: EventBus) -> None:
        self.repository = repository
        self.event_bus = event_bus

    async def execute(self, command: ChangePeriodCommand) -> Period:
        period = await self.repository.get_by_id(command.period_id)
        if period is None:
            raise ResourceNotFoundError("El periodo no existe.")
        period.close()
        await self.repository.update(period)
        await self.event_bus.publish(
            PeriodClosed(
                actor_id=command.actor_id,
                aggregate_type="period",
                aggregate_id=period.id,
                action="closed",
                data={"name": period.name},
            )
        )
        return period
