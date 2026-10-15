"""Contrato del ejercicio anual; la estructura reside en cedula_schemas."""

from datetime import date

from pydantic import BaseModel, Field

from ..domain.entities import PoaExercise
from ..domain.value_objects import PoaExerciseStatus


class CrearEjercicioRequest(BaseModel):
    anio: int = Field(ge=2000, le=2200)
    #: El POA con el que se formula el año. Es obligatorio y sin valor por
    #: omisión: no hay "el POA vigente" que adivinar. El tope es el de la columna
    #: (un entero de 32 bits): un id mayor no es un POA que no existe sino un
    #: valor que PostgreSQL ni acepta, y contestaría 500 donde el contrato es 404.
    catalogo_id: int = Field(ge=1, le=2_147_483_647)
    fecha_limite_formulacion: date | None = None


class DevolverEjercicioRequest(BaseModel):
    comentario: str = Field(
        min_length=1,
        description="Obligatorio: Planeación debe saber qué corregir.",
    )


class EjercicioRespuesta(BaseModel):
    id: int
    anio: int
    catalogo_id: int
    #: El nombre del POA, para mostrarlo: un id no se le muestra a nadie.
    catalogo_nombre: str | None
    estado: PoaExerciseStatus
    fecha_limite_formulacion: date | None
    comentario_revision: str | None
    total_cedulas: int = 0

    @classmethod
    def from_domain(
        cls, item: PoaExercise, *, catalogo_nombre: str | None, total_cedulas: int = 0
    ) -> "EjercicioRespuesta":
        # `catalogo_nombre` es obligatorio a propósito: el nombre sale del POA,
        # no del ejercicio, y un endpoint que lo olvidara contestaría sin él en
        # silencio. Así, olvidarlo falla en el acto.
        return cls(
            id=item.id,
            anio=item.year,
            catalogo_id=item.catalog_id,
            catalogo_nombre=catalogo_nombre,
            estado=item.status,
            fecha_limite_formulacion=item.formulation_deadline,
            comentario_revision=item.review_comment,
            total_cedulas=total_cedulas,
        )
