"""Crear un periodo sin persistencia acoplada."""

from app.shared.application.event_bus import EventBus
from app.shared.domain.exceptions import ConflictError

from ...domain.entities import Period
from ...domain.events import PeriodCreated
from ...domain.ports.repository import PeriodRepository
from ..dto import CreatePeriodCommand


class CreatePeriod:
    def __init__(self, repository: PeriodRepository, event_bus: EventBus) -> None:
        self.repository = repository
        self.event_bus = event_bus

    async def execute(self, command: CreatePeriodCommand) -> Period:
        for existing in await self.repository.list():
            overlaps = command.starts_on < existing.ends_on and command.ends_on > existing.starts_on
            if overlaps:
                raise ConflictError("Las fechas se traslapan con otro periodo.")

        period = Period.create(
            name=command.name,
            starts_on=command.starts_on,
            ends_on=command.ends_on,
            period_type=command.period_type,
            periodicity=command.periodicity,
            year=command.year,
        )
        await self.repository.add(period)
        await self.event_bus.publish(
            PeriodCreated(
                actor_id=command.actor_id,
                aggregate_type="period",
                aggregate_id=period.id,
                action="created",
                data={
                    "name": period.name,
                    "type": period.period_type.value,
                    "periodicity": period.periodicity.value if period.periodicity else None,
                    "year": period.year,
                    "starts_on": period.starts_on.isoformat(),
                    "ends_on": period.ends_on.isoformat(),
                },
            )
        )
        return period
