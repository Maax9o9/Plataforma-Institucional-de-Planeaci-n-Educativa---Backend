from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.shared.domain.exceptions import ResourceNotFoundError

from ...domain.ports.strategic_tree_repository import StrategicTreeRepository
from ...domain.strategic_tree_entities import StrategicNode


class CreateStrategicNode:
    def __init__(self, repository: StrategicTreeRepository) -> None:
        self.repository = repository

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
        return node


class UpdateStrategicNode:
    def __init__(self, repository: StrategicTreeRepository) -> None:
        self.repository = repository

    async def execute(self, node_id: int, changes: dict[str, Any]) -> StrategicNode:
        node = await _existing(self.repository, node_id)
        updated = replace(node, **changes)
        await self.repository.update(updated)
        return updated


class DeactivateStrategicNode:
    def __init__(self, repository: StrategicTreeRepository) -> None:
        self.repository = repository

    async def execute(self, node_id: int) -> StrategicNode:
        node = await _existing(self.repository, node_id)
        retired = replace(node, is_active=False)
        await self.repository.update(retired)
        return retired


async def _existing(repository: StrategicTreeRepository, node_id: int) -> StrategicNode:
    node = await repository.get_by_id(node_id)
    if node is None:
        raise ResourceNotFoundError("El nodo no existe.")
    return node
