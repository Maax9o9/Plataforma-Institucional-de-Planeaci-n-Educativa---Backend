"""Repositorio temporal de tipos de indicador."""

from __future__ import annotations

from itertools import count

from app.shared.domain.exceptions import ConflictError

from ..domain.reference_entities import ReferenceItem


class InMemoryReferenceRepository:
    def __init__(self) -> None:
        self._items: dict[int, ReferenceItem] = {}
        self._next_id = count(1)

    async def add(self, item: ReferenceItem) -> None:
        if item.id == 0:
            item.id = next(self._next_id)
        if any(existing.key == item.key for existing in self._items.values()):
            raise ConflictError("La clave del catalogo ya existe.")
        self._items[item.id] = item

    async def get_by_id(self, item_id: int) -> ReferenceItem | None:
        return self._items.get(item_id)

    async def list(self, *, active_only: bool = True) -> list[ReferenceItem]:
        items = list(self._items.values())
        return [item for item in items if item.is_active] if active_only else items

    async def update(self, item: ReferenceItem) -> None:
        item.version += 1
        self._items[item.id] = item
