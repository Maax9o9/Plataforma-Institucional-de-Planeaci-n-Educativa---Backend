"""Ejercicio anual compartido por las cédulas POA."""

from __future__ import annotations

from dataclasses import dataclass

from app.shared.domain.base_entity import BaseEntity
from app.shared.domain.exceptions import ValidationError


@dataclass(kw_only=True)
class PoaExercise(BaseEntity):
    year: int

    @classmethod
    def create(cls, year: int) -> PoaExercise:
        if not 2000 <= year <= 2200:
            raise ValidationError("El año del ejercicio POA no es válido.")
        return cls(year=year)
