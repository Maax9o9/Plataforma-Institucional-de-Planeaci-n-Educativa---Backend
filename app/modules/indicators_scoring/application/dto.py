"""DTOs de scoring."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CalculateEvaluationCommand:
    capture_id: int
    indicator_id: int
    period_id: int


@dataclass(frozen=True)
class UpdateThresholdsCommand:
    green: int
    yellow: int
    actor_id: int
