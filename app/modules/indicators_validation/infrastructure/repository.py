"""Repositorio en memoria del historial de estados."""

from __future__ import annotations

from itertools import count

from ..domain.entities import StateChange


class InMemoryStateChangeRepository:
    def __init__(self) -> None:
        self._items: list[StateChange] = []
        self._next_id = count(1)

    async def add(self, change: StateChange) -> None:
        if change.id == 0:
            change.id = next(self._next_id)
        self._items.append(change)

    async def list_for_capture(self, capture_id: int) -> list[StateChange]:
        return [
            item
            for item in self._items
            if item.entity == "captura" and item.entity_id == capture_id
        ]

    async def list_for_poa_advance(self, advance_id: int) -> list[StateChange]:
        return [
            item
            for item in self._items
            if item.entity == "poa_avance" and item.entity_id == advance_id
        ]
