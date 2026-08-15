"""Eventos del flujo de validacion."""

from dataclasses import dataclass

from app.shared.domain.domain_event import DomainEvent


@dataclass(frozen=True)
class CaptureValidated(DomainEvent):
    pass


@dataclass(frozen=True)
class CaptureRejected(DomainEvent):
    pass
