"""Puertos del dueño de la tabla capturas."""

from __future__ import annotations

from typing import Protocol

from ..entities import Capture


class CaptureRepository(Protocol):
    async def add(self, capture: Capture) -> None: ...

    async def get_by_id(self, capture_id: int) -> Capture | None: ...

    async def get_by_indicator_period(
        self, indicator_id: int, period_id: int
    ) -> Capture | None: ...

    async def update(self, capture: Capture) -> None: ...

    async def list_by_capturer(
        self,
        capturer_id: int,
        period_id: int | None = None,
    ) -> list[Capture]: ...

    async def list_by_indicator(self, indicator_id: int) -> list[Capture]: ...

    async def update_evaluation(
        self,
        capture_id: int,
        progress_percentage,
        semaphore: str,
    ) -> None: ...

    async def reset_validated_for_period(self, period_id: int, actor_id: int) -> list[int]: ...


class ReferenceReader(Protocol):
    async def get_by_id(self, item_id: int): ...


class EvidenceReader(Protocol):
    async def has_for(self, entity, entity_id: int) -> bool: ...
