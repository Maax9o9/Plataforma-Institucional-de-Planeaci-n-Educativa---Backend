"""Contrato de lectura y escritura de periodos."""

from __future__ import annotations

from typing import Protocol

from ..entities import Period


class PeriodRepository(Protocol):
    async def add(self, period: Period) -> None: ...

    async def get_by_id(self, period_id: int) -> Period | None: ...

    async def list(self) -> list[Period]: ...

    async def update(self, period: Period) -> None: ...

    async def delete(self, period_id: int) -> None: ...
