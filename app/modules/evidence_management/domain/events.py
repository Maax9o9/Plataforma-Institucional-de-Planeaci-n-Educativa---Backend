"""Eventos de evidencias."""

from dataclasses import dataclass

from app.shared.domain.domain_event import DomainEvent


@dataclass(frozen=True)
class EvidenceAttached(DomainEvent):
    pass


@dataclass(frozen=True)
class EvidenceReplaced(DomainEvent):
    pass
