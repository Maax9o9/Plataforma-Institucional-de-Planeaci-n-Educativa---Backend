"""Eventos de cambios del catalogo de indicadores."""

from dataclasses import dataclass

from app.shared.domain.domain_event import DomainEvent


@dataclass(frozen=True)
class IndicatorCreated(DomainEvent):
    pass


@dataclass(frozen=True)
class IndicatorUpdated(DomainEvent):
    pass


@dataclass(frozen=True)
class IndicatorDeactivated(DomainEvent):
    pass


@dataclass(frozen=True)
class IndicatorBaselineCreated(DomainEvent):
    pass


@dataclass(frozen=True)
class IndicatorGoalCreated(DomainEvent):
    pass


@dataclass(frozen=True)
class IndicatorPeriodicityChanged(DomainEvent):
    pass
