"""Contrato del ejercicio anual; la estructura reside en cedula_schemas."""

from datetime import date

from pydantic import BaseModel, Field

from ..domain.entities import PoaExercise
from ..domain.value_objects import PoaExerciseStatus


class CrearEjercicioRequest(BaseModel):
    anio: int = Field(ge=2000, le=2200)
    fecha_limite_formulacion: date | None = None


class DevolverEjercicioRequest(BaseModel):
    comentario: str = Field(
        min_length=1,
        description="Obligatorio: Planeación debe saber qué corregir.",
    )


class EjercicioRespuesta(BaseModel):
    id: int
    anio: int
    estado: PoaExerciseStatus
    fecha_limite_formulacion: date | None
    comentario_revision: str | None
    total_cedulas: int = 0

    @classmethod
    def from_domain(cls, item: PoaExercise, *, total_cedulas: int = 0) -> "EjercicioRespuesta":
        return cls(
            id=item.id,
            anio=item.year,
            estado=item.status,
            fecha_limite_formulacion=item.formulation_deadline,
            comentario_revision=item.review_comment,
            total_cedulas=total_cedulas,
        )
