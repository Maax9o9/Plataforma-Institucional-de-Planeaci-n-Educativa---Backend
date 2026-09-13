"""Repositorio temporal de periodos."""

from __future__ import annotations

import asyncio
from itertools import count

from ..domain.entities import Period


class InMemoryPeriodRepository:
    def __init__(self) -> None:
        self._periods: dict[int, Period] = {}
        self._next_id = count(1)
        self._lock = asyncio.Lock()

    async def add(self, period: Period) -> None:
        async with self._lock:
            if period.id == 0:
                period.id = next(self._next_id)
            self._periods[period.id] = period

    async def get_by_id(self, period_id: int) -> Period | None:
        return self._periods.get(period_id)

    async def list(self) -> list[Period]:
        return sorted(self._periods.values(), key=lambda period: period.starts_on)

    async def update(self, period: Period) -> None:
        async with self._lock:
            period.version += 1
            self._periods[period.id] = period

    async def delete(self, period_id: int) -> None:
        async with self._lock:
            self._periods.pop(period_id, None)
