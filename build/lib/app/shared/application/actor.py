"""Contexto minimo del actor para politicas de aplicacion."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ActorContext:
    """Evita acoplar casos de uso a la entidad concreta de identidad."""

    id: int
    roles: frozenset[str]
    area_id: int | None

    @classmethod
    def from_user(cls, user) -> ActorContext:
        return cls(
            id=user.id,
            roles=frozenset(
                role.value if hasattr(role, "value") else str(role) for role in user.roles
            ),
            area_id=user.area_id,
        )

    def has_any_role(self, *roles: str) -> bool:
        return bool(self.roles.intersection(roles))

    @property
    def is_planning(self) -> bool:
        return self.has_any_role("planeacion", "planeacion_admin", "admin_sistema")
