"""Eventos del ciclo de vida de periodos."""

from dataclasses import dataclass

from app.shared.domain.domain_event import DomainEvent


@dataclass(frozen=True)
class PeriodCreated(DomainEvent):
    pass


@dataclass(frozen=True)
class PeriodOpened(DomainEvent):
    pass


@dataclass(frozen=True)
class PeriodClosed(DomainEvent):
    pass


@dataclass(frozen=True)
class PeriodReopened(DomainEvent):
    pass
