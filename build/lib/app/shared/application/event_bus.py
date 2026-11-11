"""Contrato del bus de eventos in-process."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

from app.shared.domain.domain_event import DomainEvent

EventHandler = Callable[[DomainEvent], Awaitable[None] | None]


class EventBus(Protocol):
    def subscribe(self, event_type: type[DomainEvent], handler: EventHandler) -> None:
        """Registra un consumidor para una clase de evento."""

    async def publish(self, event: DomainEvent) -> None:
        """Publica el evento a todos sus consumidores."""
