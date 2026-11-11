"""Estrategia reutilizable para resolver umbrales de semaforizacion."""

from __future__ import annotations

from dataclasses import dataclass

from app.shared.domain.exceptions import ValidationError


@dataclass(frozen=True)
class Thresholds:
    green: int
    yellow: int


class ThresholdResolver:
    def resolve(self, indicator, global_thresholds: Thresholds) -> Thresholds:
        if indicator.green_threshold is None and indicator.yellow_threshold is None:
            return global_thresholds
        if indicator.green_threshold is None or indicator.yellow_threshold is None:
            raise ValidationError("Los umbrales personalizados estan incompletos.")
        return Thresholds(indicator.green_threshold, indicator.yellow_threshold)


def calculate_semaphore(progress: float, thresholds: Thresholds) -> str:
    if progress >= thresholds.green:
        return "verde"
    if progress >= thresholds.yellow:
        return "amarillo"
    return "rojo"
