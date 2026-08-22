"""Configuracion global de semaforos."""

from app.shared.application.event_bus import EventBus
from app.shared.domain.exceptions import ValidationError

from ...domain.events import ThresholdsUpdated
from ...domain.ports.repositories import ThresholdConfigRepository
from ...domain.strategies import Thresholds
from ..dto import UpdateThresholdsCommand


class UpdateGlobalThresholds:
    def __init__(self, repository: ThresholdConfigRepository, event_bus: EventBus) -> None:
        self.repository = repository
        self.event_bus = event_bus

    async def execute(self, command: UpdateThresholdsCommand) -> Thresholds:
        if not 0 <= command.yellow < command.green <= 100:
            raise ValidationError("Los umbrales deben cumplir 0 <= amarillo < verde <= 100.")
        previous = await self.repository.get()
        thresholds = Thresholds(green=command.green, yellow=command.yellow)
        await self.repository.update(thresholds, command.actor_id)
        await self.event_bus.publish(
            ThresholdsUpdated(
                actor_id=command.actor_id,
                aggregate_type="system_config",
                aggregate_id=1,
                action="thresholds_updated",
                data={
                    "previous": {"green": previous.green, "yellow": previous.yellow},
                    "current": {"green": thresholds.green, "yellow": thresholds.yellow},
                },
            )
        )
        return thresholds


class UpdateIndicatorThresholds:
    def __init__(self, indicator_repository, event_bus) -> None:
        self.indicator_repository = indicator_repository
        self.event_bus = event_bus

    async def execute(
        self,
        indicator_id: int,
        green: int | None,
        yellow: int | None,
        actor_id: int,
    ):
        indicator = await self.indicator_repository.get_by_id(indicator_id)
        if indicator is None:
            from app.shared.domain.exceptions import ResourceNotFoundError

            raise ResourceNotFoundError("El indicador no existe.")
        previous = {
            "green": indicator.green_threshold,
            "yellow": indicator.yellow_threshold,
        }
        indicator.set_thresholds(green, yellow)
        await self.indicator_repository.update(indicator)
        await self.event_bus.publish(
            ThresholdsUpdated(
                actor_id=actor_id,
                aggregate_type="indicator",
                aggregate_id=indicator.id,
                action="thresholds_updated",
                data={
                    "previous": previous,
                    "current": {"green": green, "yellow": yellow},
                },
            )
        )
        return indicator
