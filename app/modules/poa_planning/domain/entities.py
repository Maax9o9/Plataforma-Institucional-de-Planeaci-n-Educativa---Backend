"""Entidades de la estructura anual del POA."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.shared.domain.base_entity import BaseEntity
from app.shared.domain.exceptions import ValidationError


@dataclass(kw_only=True)
class PoaExercise(BaseEntity):
    year: int

    @classmethod
    def create(cls, year: int) -> PoaExercise:
        if not 2000 <= year <= 2200:
            raise ValidationError("El anio del ejercicio POA no es valido.")
        return cls(year=year)


@dataclass(kw_only=True)
class PoaProcess(BaseEntity):
    exercise_id: int
    name: str
    area_id: int

    @classmethod
    def create(cls, *, exercise_id: int, name: str, area_id: int) -> PoaProcess:
        if not name.strip():
            raise ValidationError("El nombre del proceso es obligatorio.")
        return cls(exercise_id=exercise_id, name=name.strip(), area_id=area_id)


@dataclass(kw_only=True)
class PoaObjective(BaseEntity):
    process_id: int
    poa_indicator: str | None
    objective: str

    @classmethod
    def create(cls, *, process_id: int, poa_indicator: str | None, objective: str) -> PoaObjective:
        if not objective.strip():
            raise ValidationError("El objetivo POA es obligatorio.")
        return cls(
            process_id=process_id,
            poa_indicator=poa_indicator,
            objective=objective.strip(),
        )


@dataclass(kw_only=True)
class PoaActivity(BaseEntity):
    objective_id: int
    description: str
    unit: str
    annual_goal: Decimal
    observations: str | None
    responsible_id: int

    @classmethod
    def create(
        cls,
        *,
        objective_id: int,
        description: str,
        unit: str,
        annual_goal: Decimal,
        observations: str | None,
        responsible_id: int,
    ) -> PoaActivity:
        if not description.strip() or not unit.strip():
            raise ValidationError("Descripcion y unidad de medida son obligatorias.")
        if annual_goal < 0:
            raise ValidationError("La meta anual no puede ser negativa.")
        return cls(
            objective_id=objective_id,
            description=description.strip(),
            unit=unit.strip(),
            annual_goal=annual_goal,
            observations=observations,
            responsible_id=responsible_id,
        )

    def update_details(
        self,
        *,
        description: str | None = None,
        unit: str | None = None,
        annual_goal: Decimal | None = None,
        observations: str | None = None,
        responsible_id: int | None = None,
    ) -> None:
        if description is not None:
            self.description = description.strip()
        if unit is not None:
            self.unit = unit.strip()
        if annual_goal is not None:
            if annual_goal < 0:
                raise ValidationError("La meta anual no puede ser negativa.")
            self.annual_goal = annual_goal
        if observations is not None:
            self.observations = observations
        if responsible_id is not None:
            self.responsible_id = responsible_id
        self.touch()
