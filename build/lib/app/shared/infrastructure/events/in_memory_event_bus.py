"""Bus de eventos en memoria para desarrollo y pruebas."""

from __future__ import annotations

import inspect
from collections import defaultdict

from app.shared.application.event_bus import EventHandler
from app.shared.domain.domain_event import DomainEvent


class InMemoryEventBus:
    def __init__(self) -> None:
        self._handlers: defaultdict[type[DomainEvent], list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: type[DomainEvent], handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)

    async def publish(self, event: DomainEvent) -> None:
        for event_type, handlers in self._handlers.items():
            if not isinstance(event, event_type):
                continue
            for handler in handlers:
                result = handler(event)
                if inspect.isawaitable(result):
                    await result
