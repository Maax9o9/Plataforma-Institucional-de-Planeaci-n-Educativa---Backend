"""Schemas HTTP de planeacion POA."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from ..domain.entities import PoaActivity, PoaExercise, PoaObjective, PoaProcess


class CrearEjercicioRequest(BaseModel):
    anio: int = Field(ge=2000, le=2200, examples=[2026])


class CrearProcesoRequest(BaseModel):
    ejercicio_id: int
    nombre: str = Field(min_length=1, max_length=300)
    area_id: int


class CrearObjetivoRequest(BaseModel):
    proceso_id: int
    indicador_poa: str | None = None
    objetivo: str = Field(min_length=1)


class CrearActividadRequest(BaseModel):
    objetivo_id: int
    descripcion: str = Field(min_length=1)
    unidad_medida: str = Field(min_length=1, max_length=100)
    meta_anual: Decimal = Field(ge=0)
    observaciones: str | None = None
    responsable_id: int


class ActualizarActividadRequest(BaseModel):
    descripcion: str | None = None
    unidad_medida: str | None = None
    meta_anual: Decimal | None = Field(default=None, ge=0)
    observaciones: str | None = None
    responsable_id: int | None = None


class EjercicioRespuesta(BaseModel):
    id: int
    anio: int

    @classmethod
    def from_domain(cls, item: PoaExercise) -> EjercicioRespuesta:
        return cls(id=item.id, anio=item.year)


class ProcesoRespuesta(BaseModel):
    id: int
    ejercicio_id: int
    nombre: str
    area_id: int

    @classmethod
    def from_domain(cls, item: PoaProcess) -> ProcesoRespuesta:
        return cls(
            id=item.id, ejercicio_id=item.exercise_id, nombre=item.name, area_id=item.area_id
        )


class ObjetivoRespuesta(BaseModel):
    id: int
    proceso_id: int
    indicador_poa: str | None
    objetivo: str

    @classmethod
    def from_domain(cls, item: PoaObjective) -> ObjetivoRespuesta:
        return cls(
            id=item.id,
            proceso_id=item.process_id,
            indicador_poa=item.poa_indicator,
            objetivo=item.objective,
        )


class ActividadRespuesta(BaseModel):
    id: int
    objetivo_id: int
    descripcion: str
    unidad_medida: str
    meta_anual: Decimal
    observaciones: str | None
    responsable_id: int

    @classmethod
    def from_domain(cls, item: PoaActivity) -> ActividadRespuesta:
        return cls(
            id=item.id,
            objetivo_id=item.objective_id,
            descripcion=item.description,
            unidad_medida=item.unit,
            meta_anual=item.annual_goal,
            observaciones=item.observations,
            responsable_id=item.responsible_id,
        )
