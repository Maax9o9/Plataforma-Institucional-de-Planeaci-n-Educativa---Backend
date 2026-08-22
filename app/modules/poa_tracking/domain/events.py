from dataclasses import dataclass

from app.shared.domain.domain_event import DomainEvent


@dataclass(frozen=True)
class PoaAdvanceChanged(DomainEvent):
    pass
