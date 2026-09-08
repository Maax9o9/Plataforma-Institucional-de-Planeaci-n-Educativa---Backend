"""Contrato del ejercicio anual; la estructura reside en cedula_schemas."""

from pydantic import BaseModel, Field

from ..domain.entities import PoaExercise


class CrearEjercicioRequest(BaseModel):
    anio: int = Field(ge=2000, le=2200)


class EjercicioRespuesta(BaseModel):
    id: int
    anio: int

    @classmethod
    def from_domain(cls, item: PoaExercise) -> "EjercicioRespuesta":
        return cls(id=item.id, anio=item.year)
