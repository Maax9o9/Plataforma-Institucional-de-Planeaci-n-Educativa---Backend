"""Configuracion global de semaforos."""

from app.shared.application.event_bus import EventBus
from app.shared.domain.exceptions import ValidationError

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
        thresholds = Thresholds(green=command.green, yellow=command.yellow)
        await self.repository.update(thresholds, command.actor_id)
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
        indicator.set_thresholds(green, yellow)
        await self.indicator_repository.update(indicator)
        return indicator
