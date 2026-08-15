"""Repositorio en memoria de avances POA."""

from __future__ import annotations

from itertools import count

from ...indicators_capture.domain.value_objects import CaptureStatus
from ..domain.entities import PoaAdvance


class InMemoryPoaAdvanceRepository:
    def __init__(self) -> None:
        self._items: dict[int, PoaAdvance] = {}
        self._next_id = count(1)

    async def add(self, item: PoaAdvance) -> None:
        if item.id == 0:
            item.id = next(self._next_id)
        self._items[item.id] = item

    async def get_by_id(self, item_id: int) -> PoaAdvance | None:
        return self._items.get(item_id)

    async def get_by_activity_quarter(self, activity_id: int, quarter: int) -> PoaAdvance | None:
        return next(
            (
                item
                for item in self._items.values()
                if item.activity_id == activity_id and item.quarter == quarter
            ),
            None,
        )

    async def update(self, item: PoaAdvance) -> None:
        self._items[item.id] = item

    async def list_by_activity(self, activity_id: int) -> list[PoaAdvance]:
        return sorted(
            [item for item in self._items.values() if item.activity_id == activity_id],
            key=lambda item: item.quarter,
        )

    async def list_by_capturer(self, capturer_id: int) -> list[PoaAdvance]:
        return sorted(
            [item for item in self._items.values() if item.capturer_id == capturer_id],
            key=lambda item: item.id,
        )

    async def has_validated_for_activity(self, activity_id: int) -> bool:
        return any(
            item.activity_id == activity_id and item.status.value == "validado"
            for item in self._items.values()
        )

    async def reset_validated_for_period(self, period_id: int, actor_id: int) -> None:
        for item in self._items.values():
            if item.period_id == period_id and item.status.value == "validado":
                item.status = CaptureStatus.DRAFT
                item.touch()
