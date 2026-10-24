"""Eventos de cambios en catalogos."""

from dataclasses import dataclass

from app.shared.domain.domain_event import DomainEvent


@dataclass(frozen=True)
class AreaCreated(DomainEvent):
    pass


@dataclass(frozen=True)
class InstrumentCreated(DomainEvent):
    pass


@dataclass(frozen=True)
class AreaUpdated(DomainEvent):
    pass


@dataclass(frozen=True)
class AreaDeactivated(DomainEvent):
    pass


@dataclass(frozen=True)
class InstrumentUpdated(DomainEvent):
    pass


@dataclass(frozen=True)
class InstrumentDeactivated(DomainEvent):
    pass


@dataclass(frozen=True)
class StrategicNodeCreated(DomainEvent):
    pass


@dataclass(frozen=True)
class StrategicNodeUpdated(DomainEvent):
    pass


@dataclass(frozen=True)
class StrategicNodeDeactivated(DomainEvent):
    pass
