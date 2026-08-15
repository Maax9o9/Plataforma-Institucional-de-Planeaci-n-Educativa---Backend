"""Repositorios en memoria del catalogo."""

from __future__ import annotations

import asyncio
from itertools import count

from app.shared.domain.exceptions import ConflictError

from ..domain.entities import Area, Instrument


class InMemoryAreaRepository:
    def __init__(self) -> None:
        self._items: dict[int, Area] = {}
        self._next_id = count(1)
        self._lock = asyncio.Lock()

    async def add(self, area: Area) -> None:
        async with self._lock:
            if area.code in self._items:
                raise ConflictError("Ya existe un area con ese codigo.")
            if area.id == 0:
                area.id = next(self._next_id)
            self._items[area.id] = area

    async def list(self, *, active_only: bool = True) -> list[Area]:
        values = list(self._items.values())
        return [area for area in values if area.is_active] if active_only else values

    async def get_by_id(self, area_id: int) -> Area | None:
        return self._items.get(area_id)

    async def update(self, area: Area) -> None:
        async with self._lock:
            self._items[area.id] = area


class InMemoryInstrumentRepository:
    def __init__(self) -> None:
        self._items: dict[int, Instrument] = {}
        self._next_id = count(1)
        self._lock = asyncio.Lock()

    async def add(self, instrument: Instrument) -> None:
        async with self._lock:
            if instrument.code in self._items:
                raise ConflictError("Ya existe un instrumento con ese codigo.")
            if instrument.id == 0:
                instrument.id = next(self._next_id)
            self._items[instrument.id] = instrument

    async def list(self, *, active_only: bool = True) -> list[Instrument]:
        values = list(self._items.values())
        return (
            [instrument for instrument in values if instrument.is_active] if active_only else values
        )

    async def get_by_id(self, instrument_id: int) -> Instrument | None:
        return self._items.get(instrument_id)

    async def update(self, instrument: Instrument) -> None:
        async with self._lock:
            self._items[instrument.id] = instrument
