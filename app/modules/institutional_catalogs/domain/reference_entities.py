"""Entidades de catalogos auxiliares usados por indicadores."""

from __future__ import annotations

from dataclasses import dataclass

from app.shared.domain.base_entity import BaseEntity
from app.shared.domain.exceptions import ValidationError


@dataclass(kw_only=True)
class ReferenceItem(BaseEntity):
    key: str
    name: str
    is_active: bool = True

    @classmethod
    def create(cls, *, key: str, name: str) -> ReferenceItem:
        if not key.strip() or not name.strip():
            raise ValidationError("Clave y nombre son obligatorios.")
        return cls(key=key.strip().upper(), name=name.strip())

    def deactivate(self) -> None:
        self.is_active = False
        self.touch()

    def update_details(self, *, key: str | None = None, name: str | None = None) -> None:
        if key is not None:
            if not key.strip():
                raise ValidationError("La clave no puede estar vacia.")
            self.key = key.strip().upper()
        if name is not None:
            if not name.strip():
                raise ValidationError("El nombre no puede estar vacio.")
            self.name = name.strip()
        self.touch()
