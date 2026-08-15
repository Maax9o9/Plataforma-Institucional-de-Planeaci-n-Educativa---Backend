"""Alta de areas sin permitir eliminacion fisica."""

from app.shared.application.event_bus import EventBus
from app.shared.domain.exceptions import ConflictError

from ...domain.entities import Area
from ...domain.events import AreaCreated
from ...domain.ports.repositories import AreaRepository
from ..dto import CreateAreaCommand


class CreateArea:
    def __init__(self, repository: AreaRepository, event_bus: EventBus) -> None:
        self.repository = repository
        self.event_bus = event_bus

    async def execute(self, command: CreateAreaCommand) -> Area:
        existing_codes = {area.code for area in await self.repository.list(active_only=False)}
        if command.code.strip().upper() in existing_codes:
            raise ConflictError("Ya existe un area con ese codigo.")
        area = Area.create(code=command.code, name=command.name, parent_id=command.parent_id)
        await self.repository.add(area)
        await self.event_bus.publish(
            AreaCreated(
                actor_id=command.actor_id,
                aggregate_type="area",
                aggregate_id=area.id,
                action="created",
                data={"code": area.code, "name": area.name},
            )
        )
        return area
