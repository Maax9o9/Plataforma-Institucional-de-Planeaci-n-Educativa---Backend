"""Alta del ejercicio anual de las cédulas."""

from app.shared.application.event_bus import EventBus

from ...domain.entities import PoaExercise
from ...domain.events import PoaStructureChanged
from ...domain.ports.cedula_repository import PoaFormRepository
from ...domain.ports.repositories import PoaRepository
from ..dto import CreateExerciseCommand
from .manage_catalog import ensure_catalog_exists


class CreateExercise:
    def __init__(
        self, repository: PoaRepository, form_repository: PoaFormRepository, event_bus: EventBus
    ) -> None:
        self.repository = repository
        self.form_repository = form_repository
        self.event_bus = event_bus

    async def execute(self, command: CreateExerciseCommand) -> PoaExercise:
        item = PoaExercise.create(
            command.year,
            catalog_id=command.catalog_id,
            formulation_deadline=command.formulation_deadline,
        )
        # El POA tiene que existir. Sin esta comprobación, en memoria un id
        # inventado dejaría un ejercicio colgando de la nada, y en PostgreSQL
        # reventaría con la llave foránea cruda sin decir que el POA es lo que
        # no está: el mismo hueco que cierran los `save_*` del catálogo.
        await ensure_catalog_exists(self.form_repository, command.catalog_id)
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
