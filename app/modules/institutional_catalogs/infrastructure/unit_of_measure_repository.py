"""Repositorio en memoria del catalogo de unidades de medida."""

from __future__ import annotations

from itertools import count

from app.shared.domain.exceptions import ConflictError

from ..domain.unit_of_measure_entities import UnitOfMeasure
from .unit_of_measure_seed import UNIDADES_MEDIDA_SEMILLA


class InMemoryUnitOfMeasureRepository:
    def __init__(self) -> None:
        # La migracion 0032 siembra estas mismas 20 unidades en PostgreSQL:
        # se precargan aqui para que memoria y PostgreSQL respondan igual.
        self._next_id = count(1)
        self._items: dict[int, UnitOfMeasure] = {}
        for seed in UNIDADES_MEDIDA_SEMILLA:
            item_id = next(self._next_id)
            self._items[item_id] = UnitOfMeasure(
                id=item_id,
                key=seed["clave"],
                name=seed["nombre"],
                plural=seed["plural"],
            )

    async def add(self, item: UnitOfMeasure) -> None:
        if item.id == 0:
            item.id = next(self._next_id)
        if any(existing.key == item.key for existing in self._items.values()):
            raise ConflictError("La clave de la unidad de medida ya existe.")
        self._items[item.id] = item

    async def get_by_id(self, item_id: int) -> UnitOfMeasure | None:
        return self._items.get(item_id)

    async def list(self, *, active_only: bool = True) -> list[UnitOfMeasure]:
        items = list(self._items.values())
        return [item for item in items if item.is_active] if active_only else items

    async def update(self, item: UnitOfMeasure) -> None:
        item.version += 1
        self._items[item.id] = item
