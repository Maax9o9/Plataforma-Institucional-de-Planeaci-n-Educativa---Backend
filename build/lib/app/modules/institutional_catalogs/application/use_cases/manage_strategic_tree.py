from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.shared.application.event_bus import EventBus
from app.shared.domain.exceptions import ResourceNotFoundError

from ...domain.events import (
    StrategicNodeCreated,
    StrategicNodeDeactivated,
    StrategicNodeReactivated,
    StrategicNodeUpdated,
)
from ...domain.ports.strategic_tree_repository import StrategicTreeRepository
from ...domain.strategic_tree_entities import StrategicNode

NODO_ESTRATEGICO = "strategic_node"


class CreateStrategicNode:
    def __init__(self, repository: StrategicTreeRepository, event_bus: EventBus) -> None:
        self.repository = repository
        self.event_bus = event_bus

    async def execute(
        self,
        *,
        version_id: int,
        parent_id: int | None,
        kind: str,
        key: str,
        name: str,
        order: int,
        indicator_formula: str | None,
        actor_id: int | None,
    ) -> StrategicNode:
        node = StrategicNode(
            version_id=version_id,
            parent_id=parent_id,
            kind=kind,
            key=key,
            name=name,
            order=order,
            indicator_formula=indicator_formula,
        )
        await self.repository.add(node)
        await self.event_bus.publish(
            StrategicNodeCreated(
                actor_id=actor_id,
                aggregate_type=NODO_ESTRATEGICO,
                aggregate_id=node.id,
                action="created",
                data={"version_id": node.version_id, "key": node.key, "kind": node.kind.value},
            )
        )
        return node


class UpdateStrategicNode:
    def __init__(self, repository: StrategicTreeRepository, event_bus: EventBus) -> None:
        self.repository = repository
        self.event_bus = event_bus

    async def execute(
        self, node_id: int, changes: dict[str, Any], *, actor_id: int | None
    ) -> StrategicNode:
        node = await _existing(self.repository, node_id)
        updated = replace(node, **changes)
        await self.repository.update(updated)
        se_retira = node.is_active and not updated.is_active
        se_reactiva = updated.is_active and not node.is_active
        cambiados = sorted(
            campo for campo in changes if getattr(updated, campo) != getattr(node, campo)
        )
        campos_corregidos = [campo for campo in cambiados if campo != "is_active"]
        if campos_corregidos:
            await self.event_bus.publish(
                StrategicNodeUpdated(
                    actor_id=actor_id,
                    aggregate_type=NODO_ESTRATEGICO,
                    aggregate_id=updated.id,
                    action="updated",
                    data={"key": updated.key, "fields": campos_corregidos},
                )
            )
        if se_retira:
            await self.event_bus.publish(
                StrategicNodeDeactivated(
                    actor_id=actor_id,
                    aggregate_type=NODO_ESTRATEGICO,
                    aggregate_id=updated.id,
                    action="deactivated",
                    data={"key": updated.key},
                )
            )
        if se_reactiva:
            await self.event_bus.publish(
                StrategicNodeReactivated(
                    actor_id=actor_id,
                    aggregate_type=NODO_ESTRATEGICO,
                    aggregate_id=updated.id,
                    action="reactivated",
                    data={"key": updated.key},
                )
            )
        return updated


class DeactivateStrategicNode:
    def __init__(self, repository: StrategicTreeRepository, event_bus: EventBus) -> None:
        self.repository = repository
        self.event_bus = event_bus

    async def execute(self, node_id: int, *, actor_id: int | None) -> StrategicNode:
        node = await _existing(self.repository, node_id)
        retired = replace(node, is_active=False)
        await self.repository.update(retired)
        if node.is_active:
            await self.event_bus.publish(
                StrategicNodeDeactivated(
                    actor_id=actor_id,
                    aggregate_type=NODO_ESTRATEGICO,
                    aggregate_id=retired.id,
                    action="deactivated",
                    data={"key": retired.key},
                )
            )
        return retired


async def _existing(repository: StrategicTreeRepository, node_id: int) -> StrategicNode:
    node = await repository.get_by_id(node_id)
    if node is None:
        raise ResourceNotFoundError("El nodo no existe.")
    return node
