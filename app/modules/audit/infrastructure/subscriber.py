"""Suscriptor desacoplado: cualquier evento de dominio genera una entrada."""

from __future__ import annotations

from app.shared.application.event_bus import EventBus
from app.shared.domain.domain_event import DomainEvent

from ..domain.entities import AuditEntry
from ..domain.ports.repository import AuditRepository


def register_audit_subscriber(event_bus: EventBus, repository: AuditRepository) -> None:
    async def handle(event: DomainEvent) -> None:
        await repository.append(
            AuditEntry(
                id=event.event_id,
                event_name=event.__class__.__name__,
                occurred_at=event.occurred_at,
                actor_id=event.actor_id,
                aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id,
                action=event.action,
                data=dict(event.data),
            )
        )

    event_bus.subscribe(DomainEvent, handle)
