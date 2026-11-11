"""Editar y desactivar areas sin eliminacion fisica."""

from __future__ import annotations

from app.shared.application.event_bus import EventBus
from app.shared.domain.exceptions import ConflictError, ResourceNotFoundError

from ...domain.entities import Area
from ...domain.events import AreaDeactivated, AreaUpdated
from ...domain.ports.repositories import AreaRepository
from ..dto import ChangeCatalogStatusCommand, UpdateAreaCommand


class UpdateArea:
    def __init__(self, repository: AreaRepository, event_bus: EventBus) -> None:
        self.repository = repository
        self.event_bus = event_bus

    async def execute(self, command: UpdateAreaCommand) -> Area:
        area = await self.repository.get_by_id(command.area_id)
        if area is None:
            raise ResourceNotFoundError("El area no existe.")
        if command.expected_version is not None and command.expected_version != area.version:
            raise ConflictError(
                "El area fue modificada por otra solicitud.",
                details={"version_actual": area.version},
            )
        area.update_details(
            code=command.code,
            name=command.name,
            parent_id=command.parent_id,
            area_type=command.area_type,
            color=command.color,
        )
        await self.repository.update(area)
        await self.event_bus.publish(
            AreaUpdated(
                actor_id=command.actor_id,
                aggregate_type="area",
                aggregate_id=area.id,
                action="updated",
                data={"code": area.code, "name": area.name},
            )
        )
        return area


class DeactivateArea:
    def __init__(self, repository: AreaRepository, event_bus: EventBus) -> None:
        self.repository = repository
        self.event_bus = event_bus

    async def execute(self, command: ChangeCatalogStatusCommand) -> Area:
        area = await self.repository.get_by_id(command.item_id)
        if area is None:
            raise ResourceNotFoundError("El area no existe.")
        if command.expected_version is not None and command.expected_version != area.version:
            raise ConflictError(
                "El area fue modificada por otra solicitud.",
                details={"version_actual": area.version},
            )
        area.deactivate()
        await self.repository.update(area)
        await self.event_bus.publish(
            AreaDeactivated(
                actor_id=command.actor_id,
                aggregate_type="area",
                aggregate_id=area.id,
                action="deactivated",
                data={"code": area.code},
            )
        )
        return area
