"""Catalogo de unidades de medida de las actividades del POA.

A diferencia de ReferenceItem (criterios SEAES, tipos de indicador), esta
unidad necesita guardar tambien el plural: la actividad la muestra junto a la
meta ("3 Informes"), y el catalogo existe justo para ofrecer un par
singular/plural consistente en vez del texto libre que hoy produce
"Informe" e "Informes" como si fueran cosas distintas.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.shared.domain.base_entity import BaseEntity
from app.shared.domain.exceptions import ValidationError


@dataclass(kw_only=True)
class UnitOfMeasure(BaseEntity):
    key: str
    name: str
    plural: str
    is_active: bool = True
    version: int = 1

    @classmethod
    def create(cls, *, key: str, name: str, plural: str) -> UnitOfMeasure:
        if not key.strip() or not name.strip() or not plural.strip():
            raise ValidationError("Clave, nombre y plural son obligatorios.")
        return cls(key=key.strip().lower(), name=name.strip(), plural=plural.strip())

    def deactivate(self) -> None:
        self.is_active = False
        self.touch()

    def update_details(
        self,
        *,
        key: str | None = None,
        name: str | None = None,
        plural: str | None = None,
    ) -> None:
        if key is not None:
            if not key.strip():
                raise ValidationError("La clave no puede estar vacia.")
            self.key = key.strip().lower()
        if name is not None:
            if not name.strip():
                raise ValidationError("El nombre no puede estar vacio.")
            self.name = name.strip()
        if plural is not None:
            if not plural.strip():
                raise ValidationError("El plural no puede estar vacio.")
            self.plural = plural.strip()
        self.touch()
