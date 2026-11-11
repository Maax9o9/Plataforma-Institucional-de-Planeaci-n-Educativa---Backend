"""Repositorio en memoria de capturas."""

from __future__ import annotations

from itertools import count

from ..domain.entities import Capture
from ..domain.value_objects import CaptureStatus


class InMemoryCaptureRepository:
    def __init__(self) -> None:
        self._items: dict[int, Capture] = {}
        self._next_id = count(1)

    async def add(self, capture: Capture) -> None:
        if capture.id == 0:
            capture.id = next(self._next_id)
        self._items[capture.id] = capture

    async def get_by_id(self, capture_id: int) -> Capture | None:
        return self._items.get(capture_id)

    async def get_by_indicator_period(self, indicator_id: int, period_id: int) -> Capture | None:
        return next(
            (
                item
                for item in self._items.values()
                if item.indicator_id == indicator_id and item.period_id == period_id
            ),
            None,
        )

    async def update(self, capture: Capture) -> None:
        capture.version += 1
        self._items[capture.id] = capture

    async def list_by_capturer(
        self,
        capturer_id: int,
        period_id: int | None = None,
    ) -> list[Capture]:
        items = [item for item in self._items.values() if item.capturer_id == capturer_id]
        if period_id is not None:
            items = [item for item in items if item.period_id == period_id]
        return sorted(items, key=lambda item: item.id)

    async def list_by_indicator(self, indicator_id: int) -> list[Capture]:
        return sorted(
            [
                item
                for item in self._items.values()
                if item.indicator_id == indicator_id and item.status.value == "validado"
            ],
            key=lambda item: item.period_id,
        )

    async def update_evaluation(self, capture_id: int, progress_percentage, semaphore: str) -> None:
        capture = self._items[capture_id]
        capture.progress_percentage = progress_percentage
        capture.semaphore = semaphore
        capture.touch()

    async def list_all(self) -> list[Capture]:
        return sorted(self._items.values(), key=lambda item: item.id)

    async def reset_validated_for_period(self, period_id: int, actor_id: int) -> list[int]:
        del actor_id
        reset_ids = []
        for item in self._items.values():
            if item.period_id == period_id and item.status is CaptureStatus.VALIDATED:
                reset_ids.append(item.id)
                item.status = CaptureStatus.DRAFT
                item.progress_percentage = None
                item.semaphore = None
                item.touch()
        return reset_ids
