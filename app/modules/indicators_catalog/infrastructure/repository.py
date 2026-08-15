"""Repositorio en memoria para pruebas del catalogo de indicadores."""

from __future__ import annotations

from itertools import count

from app.shared.domain.exceptions import ConflictError

from ..domain.entities import Baseline, Goal, Indicator


class InMemoryIndicatorRepository:
    def __init__(self) -> None:
        self._items: dict[int, Indicator] = {}
        self._baselines: dict[int, Baseline] = {}
        self._goals: dict[tuple[int, int], Goal] = {}
        self._next_id = count(1)

    async def add(self, indicator: Indicator) -> None:
        if indicator.id == 0:
            indicator.id = next(self._next_id)
        self._items[indicator.id] = indicator

    async def get_by_id(self, indicator_id: int) -> Indicator | None:
        return self._items.get(indicator_id)

    async def get_by_key(self, key: str) -> Indicator | None:
        normalized = key.strip().upper()
        return next((item for item in self._items.values() if item.key == normalized), None)

    async def list(self, *, active_only: bool = False) -> list[Indicator]:
        items = list(self._items.values())
        if active_only:
            items = [item for item in items if item.is_active]
        return sorted(items, key=lambda item: item.key)

    async def update(self, indicator: Indicator) -> None:
        self._items[indicator.id] = indicator

    async def add_baseline(self, baseline: Baseline) -> None:
        if baseline.indicator_id in self._baselines:
            raise ConflictError("El indicador ya tiene una linea base.")
        self._baselines[baseline.indicator_id] = baseline

    async def add_goal(self, goal: Goal) -> None:
        key = (goal.indicator_id, goal.period_id)
        if key in self._goals:
            raise ConflictError("Ya existe una meta para el indicador y periodo.")
        self._goals[key] = goal

    async def get_goal(self, indicator_id: int, period_id: int) -> Goal | None:
        return self._goals.get((indicator_id, period_id))
