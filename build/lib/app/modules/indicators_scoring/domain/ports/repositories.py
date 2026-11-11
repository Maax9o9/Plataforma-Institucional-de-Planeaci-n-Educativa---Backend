"""Puertos de evaluacion."""

from __future__ import annotations

from typing import Protocol

from ..strategies import Thresholds


class IndicatorReader(Protocol):
    async def get_by_id(self, indicator_id: int): ...


class CaptureEvaluationWriter(Protocol):
    async def update_evaluation(
        self, capture_id: int, progress_percentage, semaphore: str
    ) -> None: ...


class GoalReader(Protocol):
    async def get_goal(self, indicator_id: int, period_id: int): ...


class ThresholdConfigRepository(Protocol):
    async def get(self) -> Thresholds: ...

    async def update(self, thresholds: Thresholds, actor_id: int) -> None: ...
