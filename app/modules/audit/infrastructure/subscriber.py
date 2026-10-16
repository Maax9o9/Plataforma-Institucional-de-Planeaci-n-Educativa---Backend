"""Suscriptor desacoplado: cualquier evento de dominio genera una entrada."""

from __future__ import annotations

from app.shared.application.event_bus import EventBus
from app.shared.domain.domain_event import DomainEvent

from ..domain.entities import AuditEntry
from ..domain.ports.repository import AuditRepository

#: Movimientos de sesion que NO pertenecen a la bitacora de negocio.
#:
#: La bitacora responde "quien hizo que con el POA": quien capturo una
#: actividad, quien la envio, quien la evaluo. Un inicio de sesion no dice nada
#: de eso, y en la practica los ahogaba: 132 de ~200 registros eran `login` y
#: `refresh`, asi que para encontrar una modificacion real habia que pasar
#: varias paginas de ruido.
#:
#: Estos eventos no dejan de importar -los intentos fallidos son lo que delata
#: a alguien intentando entrar-, solo que su lugar es `bitacora_accesos`, que
#: la migracion 0002 creo aparte justamente para poder purgarla con otra
#: politica sin tocar la bitacora inmutable.
#:
#: `password_changed` NO entra aqui aunque tambien sea de la cuenta: cambiar
#: una contrasena es un movimiento de seguridad que debe quedar registrado, y
#: ademas el cambio se revierte si su entrada de bitacora no se escribe
#: (test_password_change). Sacarlo de aqui rompe esa garantia.
ACCIONES_DE_SESION = frozenset({"login", "logout", "refresh"})


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
        if event.aggregate_type == "user" and event.action in ACCIONES_DE_SESION:
            return
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
