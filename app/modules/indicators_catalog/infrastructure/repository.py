"""Repositorio en memoria para pruebas del catalogo de indicadores."""

from __future__ import annotations

from itertools import count

from app.shared.domain.exceptions import ConflictError

from ..domain.entities import Baseline, Goal, Indicator
from ..domain.value_objects import IndicatorPeriodicity


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

    async def list_page(
        self,
        *,
        active_only: bool,
        query: str | None,
        area_id: int | None,
        responsible_id: int | None,
        instrument_id: int | None,
        criterion_id: int | None,
        periodicity: IndicatorPeriodicity | None,
        sort: str,
        descending: bool,
        offset: int,
        limit: int,
    ) -> tuple[list[Indicator], int]:
        items = await self.list(active_only=active_only)
        if query:
            normalized = query.strip().casefold()
            items = [
                item
                for item in items
                if normalized in item.key.casefold() or normalized in item.name.casefold()
            ]
        if area_id is not None:
            items = [item for item in items if item.area_id == area_id]
        if responsible_id is not None:
            items = [item for item in items if item.responsible_id == responsible_id]
        if instrument_id is not None:
            items = [item for item in items if instrument_id in item.instrument_ids]
        if criterion_id is not None:
            items = [item for item in items if criterion_id in item.criteria_ids]
        if periodicity is not None:
            items = [item for item in items if item.periodicity == periodicity]
        key = {
            "clave": lambda item: (item.key.casefold(), item.id),
            "nombre": lambda item: (item.name.casefold(), item.id),
            "periodicidad": lambda item: (item.periodicity.value, item.id),
            "actualizado_en": lambda item: (item.updated_at, item.id),
        }[sort]
        items.sort(key=key, reverse=descending)
        return items[offset : offset + limit], len(items)

    async def update(self, indicator: Indicator) -> None:
        indicator.version += 1
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

    async def get_baseline(self, indicator_id: int) -> Baseline | None:
        return self._baselines.get(indicator_id)

    async def list_goals(self, indicator_id: int) -> list[Goal]:
        return sorted(
            [item for (item_id, _), item in self._goals.items() if item_id == indicator_id],
            key=lambda item: item.period_id,
        )

    async def set_criteria(self, indicator_id: int, criteria_ids: set[int]) -> None:
        self._items[indicator_id].criteria_ids = set(criteria_ids)
        self._items[indicator_id].touch()
