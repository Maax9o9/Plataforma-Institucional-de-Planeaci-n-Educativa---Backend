"""Eventos derivados de evaluacion."""

from dataclasses import dataclass

from app.shared.domain.domain_event import DomainEvent


@dataclass(frozen=True)
class IndicatorAtRisk(DomainEvent):
    pass
