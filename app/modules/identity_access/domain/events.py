"""Eventos publicados por identidad sin conocer a sus suscriptores."""

from dataclasses import dataclass

from app.shared.domain.domain_event import DomainEvent


@dataclass(frozen=True)
class UserRegistered(DomainEvent):
    pass


@dataclass(frozen=True)
class UserLoggedIn(DomainEvent):
    pass


@dataclass(frozen=True)
class UserLoggedOut(DomainEvent):
    pass


@dataclass(frozen=True)
class UserUpdated(DomainEvent):
    pass


@dataclass(frozen=True)
class UserDeactivated(DomainEvent):
    pass


@dataclass(frozen=True)
class UserReactivated(DomainEvent):
    pass
