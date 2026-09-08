"""Entidades puras del modulo de identidad."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.shared.domain.base_entity import BaseEntity
from app.shared.domain.exceptions import ValidationError
from app.shared.domain.value_objects import Email

from .value_objects import Role


@dataclass(kw_only=True)
class User(BaseEntity):
    email: Email
    full_name: str
    password_hash: str
    roles: frozenset[Role] = field(default_factory=lambda: frozenset({Role.CONSULTA}))
    area_id: int | None = None
    is_active: bool = True
    notify_email: bool = True
    password_setup_required: bool = False
    last_access_at: datetime | None = None
    area_name: str | None = None
    version: int = 1
    password_version: int = 0

    @classmethod
    def register(
        cls,
        *,
        email: str,
        full_name: str,
        password_hash: str,
        roles: set[Role] | frozenset[Role] | None = None,
        area_id: int | None = None,
    ) -> User:
        normalized_name = full_name.strip()
        if not normalized_name:
            raise ValidationError("El nombre completo es obligatorio.")
        if len(normalized_name) > 150:
            raise ValidationError("El nombre completo no puede superar 150 caracteres.")
        selected_roles = frozenset({Role.CONSULTA} if roles is None else roles)
        if not selected_roles:
            raise ValidationError("El usuario debe tener al menos un rol.")
        return cls(
            email=Email(email),
            full_name=normalized_name,
            password_hash=password_hash,
            roles=selected_roles,
            area_id=area_id,
        )

    def deactivate(self) -> None:
        self.is_active = False
        self.touch()

    def activate(self) -> None:
        self.is_active = True
        self.touch()

    def update_details(
        self,
        *,
        email: str | None = None,
        full_name: str | None = None,
        roles: set[Role] | frozenset[Role] | None = None,
        area_id: int | None = None,
        notify_email: bool | None = None,
    ) -> None:
        if email is not None:
            self.email = Email(email)
        if full_name is not None:
            normalized_name = full_name.strip()
            if not normalized_name:
                raise ValidationError("El nombre completo es obligatorio.")
            self.full_name = normalized_name
        if roles is not None:
            selected_roles = frozenset(roles)
            if not selected_roles:
                raise ValidationError("El usuario debe tener al menos un rol.")
            self.roles = selected_roles
        if area_id is not None:
            self.area_id = area_id
        if notify_email is not None:
            self.notify_email = notify_email
        self.touch()

    def record_successful_login(self, occurred_at: datetime) -> None:
        self.last_access_at = occurred_at

    def has_any_role(self, roles: set[Role] | set[str]) -> bool:
        values = {role.value if isinstance(role, Role) else role for role in roles}
        current = {role.value for role in self.roles}
        if Role.PLANEACION_ADMIN.value in current:
            current.update({Role.PLANEACION.value, Role.ADMIN_SISTEMA.value})
        return bool(current.intersection(values))
