"""Suscriptor desacoplado: cualquier evento de dominio genera una entrada."""

from __future__ import annotations

from app.shared.application.event_bus import EventBus
from app.shared.domain.domain_event import DomainEvent

from ..domain.entities import AuditEntry
from ..domain.ports.repository import AuditRepository


def register_audit_subscriber(
    event_bus: EventBus,
    repository: AuditRepository,
    users=None,
) -> None:
    """Registra el suscriptor de bitacora.

    `users` es un lector opcional del directorio. Cuando se proporciona, el
    nombre del autor se resuelve **al escribir** la entrada y queda congelado
    ahi. Sin el, la entrada conserva solo el identificador y el nombre historico
    se pierde: un cambio posterior de nombre reatribuiria el movimiento.
    """

    async def actor_name(actor_id: int | None) -> str | None:
        if actor_id is None or users is None:
            return None
        try:
            user = await users.get_by_id(actor_id)
        except Exception:  # noqa: BLE001 - la bitacora nunca debe tumbar la operacion
            return None
        return getattr(user, "full_name", None) if user is not None else None

    async def handle(event: DomainEvent) -> None:
        await repository.append(
            AuditEntry(
                id=event.event_id,
                event_name=event.__class__.__name__,
                occurred_at=event.occurred_at,
                actor_id=event.actor_id,
                actor_name=await actor_name(event.actor_id),
                aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id,
                action=event.action,
                data=dict(event.data),
            )
        )

    event_bus.subscribe(DomainEvent, handle)
