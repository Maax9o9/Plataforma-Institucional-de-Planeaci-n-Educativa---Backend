"""Schemas HTTP de periodos."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from ..domain.entities import Period
from ..domain.value_objects import Periodicity, PeriodStatus, PeriodType


class CrearPeriodoRequest(BaseModel):
    tipo: PeriodType = Field(description="Tipo de flujo del periodo.", examples=["indicadores"])
    periodicidad: Periodicity | None = Field(
        default=None,
        description="Periodicidad obligatoria para indicadores y nula para POA.",
        examples=["mensual"],
    )
    anio: int = Field(ge=2000, le=2200, examples=[2026])
    etiqueta: str = Field(min_length=2, max_length=100, examples=["Ene-2026"])
    fecha_inicio: date = Field(description="Fecha inicial del periodo.", examples=["2026-01-01"])
    fecha_limite: date = Field(description="Fecha limite del periodo.", examples=["2026-04-30"])


class ReabrirPeriodoRequest(BaseModel):
    motivo: str = Field(
        min_length=1,
        max_length=500,
        description="Motivo obligatorio de la reapertura.",
        examples=["Correccion autorizada por Planeacion"],
    )


class PeriodoResponse(BaseModel):
    id: int
    tipo: PeriodType
    periodicidad: Periodicity | None
    anio: int
    etiqueta: str
    fecha_inicio: date
    fecha_limite: date
    estado: PeriodStatus
    motivo_reapertura: str | None = None
    reabierto_por: int | None = None

    @classmethod
    def from_domain(cls, period: Period) -> PeriodoResponse:
        return cls(
            id=period.id,
            tipo=period.period_type,
            periodicidad=period.periodicity,
            anio=period.year,
            etiqueta=period.name,
            fecha_inicio=period.starts_on,
            fecha_limite=period.ends_on,
            estado=period.status,
            motivo_reapertura=period.reopen_reason,
            reabierto_por=period.reopened_by,
        )
