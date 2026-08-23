"""Puertos de validacion y su historial."""

from __future__ import annotations

from typing import Protocol

from ....indicators_capture.domain.entities import Capture
from ..entities import StateChange


class CaptureReader(Protocol):
    async def get_by_id(self, capture_id: int) -> Capture | None: ...

    async def update(self, capture: Capture) -> None: ...


class StateChangeRepository(Protocol):
    async def add(self, change: StateChange) -> None: ...

    async def list_for_capture(self, capture_id: int) -> list[StateChange]: ...

    async def list_for_capture_page(
        self,
        capture_id: int,
        *,
        offset: int,
        limit: int,
        descending: bool,
    ) -> tuple[list[StateChange], int]: ...
