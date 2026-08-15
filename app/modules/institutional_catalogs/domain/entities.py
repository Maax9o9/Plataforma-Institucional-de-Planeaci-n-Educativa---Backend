"""Entidades de areas e instrumentos."""

from __future__ import annotations

from dataclasses import dataclass

from app.shared.domain.base_entity import BaseEntity
from app.shared.domain.exceptions import ValidationError


def _required(value: str, label: str, max_length: int) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValidationError(f"{label} es obligatorio.")
    if len(normalized) > max_length:
        raise ValidationError(f"{label} no puede superar {max_length} caracteres.")
    return normalized


@dataclass(kw_only=True)
class Area(BaseEntity):
    code: str
    name: str
    parent_id: int | None = None
    is_active: bool = True

    @classmethod
    def create(cls, *, code: str, name: str, parent_id: int | None = None) -> Area:
        normalized_code = _required(code, "El codigo del area", 30).upper()
        return cls(
            code=normalized_code,
            name=_required(name, "El nombre del area", 150),
            parent_id=parent_id,
        )

    def update_details(
        self,
        *,
        code: str | None = None,
        name: str | None = None,
        parent_id: int | None = None,
    ) -> None:
        if code is not None:
            self.code = _required(code, "El codigo del area", 30).upper()
        if name is not None:
            self.name = _required(name, "El nombre del area", 150)
        if parent_id is not None:
            self.parent_id = parent_id
        self.touch()

    def deactivate(self) -> None:
        self.is_active = False
        self.touch()

    def activate(self) -> None:
        self.is_active = True
        self.touch()


@dataclass(kw_only=True)
class Instrument(BaseEntity):
    code: str
    name: str
    description: str | None = None
    is_active: bool = True

    @classmethod
    def create(cls, *, code: str, name: str, description: str | None = None) -> Instrument:
        normalized_code = _required(code, "El codigo del instrumento", 30).upper()
        normalized_description = description.strip() if description else None
        return cls(
            code=normalized_code,
            name=_required(name, "El nombre del instrumento", 150),
            description=normalized_description,
        )

    def update_details(
        self,
        *,
        code: str | None = None,
        name: str | None = None,
        description: str | None = None,
    ) -> None:
        if code is not None:
            self.code = _required(code, "El codigo del instrumento", 30).upper()
        if name is not None:
            self.name = _required(name, "El nombre del instrumento", 150)
        if description is not None:
            self.description = description.strip()
        self.touch()

    def deactivate(self) -> None:
        self.is_active = False
        self.touch()

    def activate(self) -> None:
        self.is_active = True
        self.touch()
