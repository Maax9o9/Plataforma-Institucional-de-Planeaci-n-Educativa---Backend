"""Editar y desactivar catalogos auxiliares."""

from app.shared.application.event_bus import EventBus
from app.shared.domain.exceptions import ResourceNotFoundError

from ...domain.ports.repositories import ReferenceRepository
from ...domain.reference_entities import ReferenceItem


class UpdateReference:
    def __init__(self, repository: ReferenceRepository, event_bus: EventBus) -> None:
        self.repository = repository
        self.event_bus = event_bus

    async def execute(
        self,
        item_id: int,
        key: str | None,
        name: str | None,
        actor_id: int,
    ) -> ReferenceItem:
        item = await self.repository.get_by_id(item_id)
        if item is None:
            raise ResourceNotFoundError("El registro de catalogo no existe.")
        item.update_details(key=key, name=name)
        await self.repository.update(item)
        return item


class DeactivateReference:
    def __init__(self, repository: ReferenceRepository, event_bus: EventBus) -> None:
        self.repository = repository
        self.event_bus = event_bus

    async def execute(self, item_id: int, actor_id: int) -> ReferenceItem:
        item = await self.repository.get_by_id(item_id)
        if item is None:
            raise ResourceNotFoundError("El registro de catalogo no existe.")
        item.deactivate()
        await self.repository.update(item)
        return item
