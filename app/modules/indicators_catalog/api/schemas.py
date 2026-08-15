"""Contrato HTTP en espanol para indicadores."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from ..domain.entities import Baseline, Goal, Indicator
from ..domain.value_objects import IndicatorPeriodicity


class RegistrarIndicadorRequest(BaseModel):
    clave: str = Field(min_length=1, max_length=50, examples=["IND-01"])
    nombre: str = Field(min_length=2, max_length=300, examples=["Cobertura educativa"])
    metodo_calculo: str = Field(min_length=2, examples=["Alumnos atendidos / meta * 100"])
    unidad_medida: str = Field(min_length=1, max_length=100, examples=["Porcentaje"])
    definicion: str | None = None
    dimension: str | None = None
    documento_verificacion: str | None = None
    fuente_informacion: str | None = None
    observaciones_metodologicas: str | None = None
    tipo_indicador_id: int | None = None
    area_id: int
    responsable_id: int
    periodicidad: IndicatorPeriodicity
    instrumento_ids: set[int] = Field(default_factory=set)
    umbral_verde_min: int | None = Field(default=None, ge=0, le=100)
    umbral_amarillo_min: int | None = Field(default=None, ge=0, le=100)


class ActualizarIndicadorRequest(BaseModel):
    nombre: str | None = Field(default=None, min_length=2, max_length=300)
    metodo_calculo: str | None = None
    unidad_medida: str | None = Field(default=None, max_length=100)
    definicion: str | None = None
    dimension: str | None = None
    documento_verificacion: str | None = None
    fuente_informacion: str | None = None
    observaciones_metodologicas: str | None = None
    area_id: int | None = None
    responsable_id: int | None = None
    tipo_indicador_id: int | None = None

    @model_validator(mode="after")
    def require_one_change(self) -> ActualizarIndicadorRequest:
        if not self.model_dump(exclude_none=True):
            raise ValueError("Debe indicar al menos un campo para actualizar.")
        return self


class CambiarPeriodicidadRequest(BaseModel):
    periodicidad: IndicatorPeriodicity


class ActualizarUmbralesRequest(BaseModel):
    umbral_verde_min: int | None = Field(default=None, ge=0, le=100)
    umbral_amarillo_min: int | None = Field(default=None, ge=0, le=100)


class LineaBaseRequest(BaseModel):
    anio: int = Field(ge=2000, le=2200, examples=[2024])
    periodo: str | None = Field(default=None, max_length=50)
    valor: Decimal = Field(examples=["85.50"])


class MetaIndicadorRequest(BaseModel):
    periodo_id: int
    valor: Decimal = Field(ge=0, examples=["90.00"])


class IndicadorRespuesta(BaseModel):
    id: int
    clave: str
    nombre: str
    definicion: str | None
    metodo_calculo: str
    unidad_medida: str
    dimension: str | None
    documento_verificacion: str | None
    fuente_informacion: str | None
    observaciones_metodologicas: str | None
    tipo_indicador_id: int | None
    area_id: int
    responsable_id: int
    periodicidad: IndicatorPeriodicity
    umbral_verde_min: int | None
    umbral_amarillo_min: int | None
    activo: bool
    instrumento_ids: list[int]
    creado_en: datetime
    actualizado_en: datetime

    @classmethod
    def from_domain(cls, indicator: Indicator) -> IndicadorRespuesta:
        return cls(
            id=indicator.id,
            clave=indicator.key,
            nombre=indicator.name,
            definicion=indicator.definition,
            metodo_calculo=indicator.calculation_method,
            unidad_medida=indicator.unit,
            dimension=indicator.dimension,
            documento_verificacion=indicator.verification_document,
            fuente_informacion=indicator.information_source,
            observaciones_metodologicas=indicator.methodological_notes,
            tipo_indicador_id=indicator.indicator_type_id,
            area_id=indicator.area_id,
            responsable_id=indicator.responsible_id,
            periodicidad=indicator.periodicity,
            umbral_verde_min=indicator.green_threshold,
            umbral_amarillo_min=indicator.yellow_threshold,
            activo=indicator.is_active,
            instrumento_ids=sorted(indicator.instrument_ids),
            creado_en=indicator.created_at,
            actualizado_en=indicator.updated_at,
        )


class LineaBaseRespuesta(BaseModel):
    indicador_id: int
    anio: int
    periodo: str | None
    valor: Decimal

    @classmethod
    def from_domain(cls, baseline: Baseline) -> LineaBaseRespuesta:
        return cls(
            indicador_id=baseline.indicator_id,
            anio=baseline.year,
            periodo=baseline.period,
            valor=baseline.value,
        )


class MetaIndicadorRespuesta(BaseModel):
    indicador_id: int
    periodo_id: int
    valor: Decimal

    @classmethod
    def from_domain(cls, goal: Goal) -> MetaIndicadorRespuesta:
        return cls(
            indicador_id=goal.indicator_id,
            periodo_id=goal.period_id,
            valor=goal.value,
        )
