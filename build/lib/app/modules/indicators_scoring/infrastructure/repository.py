"""Configuracion temporal de umbrales."""

from __future__ import annotations

from app.modules.indicators_scoring.domain.strategies import Thresholds


class InMemoryThresholdConfigRepository:
    def __init__(self) -> None:
        self._thresholds = Thresholds(green=90, yellow=40)

    async def get(self) -> Thresholds:
        return self._thresholds

    async def update(self, thresholds: Thresholds, actor_id: int) -> None:
        self._thresholds = thresholds
