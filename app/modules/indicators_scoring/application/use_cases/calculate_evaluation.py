"""Calculo automatico de porcentaje y semaforo al validar."""

from __future__ import annotations

from decimal import Decimal

from app.shared.application.event_bus import EventBus
from app.shared.domain.exceptions import ResourceNotFoundError, ValidationError

from ....indicators_capture.domain.ports.repositories import CaptureRepository
from ....indicators_catalog.domain.ports.repositories import IndicatorRepository
from ...domain.events import IndicatorAtRisk
from ...domain.ports.repositories import GoalReader, ThresholdConfigRepository
from ...domain.strategies import ThresholdResolver, calculate_semaphore
from ..dto import CalculateEvaluationCommand


class CalculateEvaluation:
    def __init__(
        self,
        indicators: IndicatorRepository,
        captures: CaptureRepository,
        goals: GoalReader,
        config: ThresholdConfigRepository,
        event_bus: EventBus,
        resolver: ThresholdResolver | None = None,
    ) -> None:
        self.indicators = indicators
        self.captures = captures
        self.goals = goals
        self.config = config
        self.event_bus = event_bus
        self.resolver = resolver or ThresholdResolver()

    async def execute(self, command: CalculateEvaluationCommand):
        indicator = await self.indicators.get_by_id(command.indicator_id)
        capture = await self.captures.get_by_id(command.capture_id)
        goal = await self.goals.get_goal(command.indicator_id, command.period_id)
        if indicator is None or capture is None or goal is None:
            raise ResourceNotFoundError(
                "No existe la informacion necesaria para evaluar la captura."
            )
        if goal.value == 0:
            raise ValidationError("La meta no puede ser cero al calcular el avance.")
        progress = (Decimal(capture.result or 0) / Decimal(goal.value)) * Decimal(100)
        thresholds = self.resolver.resolve(indicator, await self.config.get())
        semaphore = calculate_semaphore(float(progress), thresholds)
        await self.captures.update_evaluation(command.capture_id, progress, semaphore)
        if semaphore in {"amarillo", "rojo"}:
            await self.event_bus.publish(
                IndicatorAtRisk(
                    actor_id=None,
                    aggregate_type="indicator",
                    aggregate_id=indicator.id,
                    action="at_risk",
                    data={"capture_id": capture.id, "semaphore": semaphore},
                )
            )
        return progress, semaphore
