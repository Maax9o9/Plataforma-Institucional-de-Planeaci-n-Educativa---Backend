"""Eventos de validacion POA."""

from dataclasses import dataclass

from app.shared.domain.domain_event import DomainEvent


@dataclass(frozen=True)
class PoaAdvanceValidated(DomainEvent):
    pass


@dataclass(frozen=True)
class PoaAdvanceRejected(DomainEvent):
    pass
