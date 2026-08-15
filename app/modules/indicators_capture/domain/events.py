"""Eventos del flujo de captura."""

from dataclasses import dataclass

from app.shared.domain.domain_event import DomainEvent


@dataclass(frozen=True)
class CaptureCreated(DomainEvent):
    pass


@dataclass(frozen=True)
class CaptureSent(DomainEvent):
    pass


@dataclass(frozen=True)
class CaptureUpdated(DomainEvent):
    pass
