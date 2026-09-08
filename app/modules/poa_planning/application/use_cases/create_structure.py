"""Alta del ejercicio anual de las cédulas."""

from app.shared.application.event_bus import EventBus

from ...domain.entities import PoaExercise
from ...domain.events import PoaStructureChanged
from ...domain.ports.repositories import PoaRepository
from ..dto import CreateExerciseCommand


class CreateExercise:
    def __init__(self, repository: PoaRepository, event_bus: EventBus) -> None:
        self.repository = repository
        self.event_bus = event_bus

    async def execute(self, command: CreateExerciseCommand) -> PoaExercise:
        item = PoaExercise.create(command.year)
        await self.repository.add_exercise(item)
        await self.event_bus.publish(
            PoaStructureChanged(
                actor_id=command.actor_id,
                aggregate_type="poa_exercise",
                aggregate_id=item.id,
                action="created",
                data={"year": item.year},
            )
        )
        return item
