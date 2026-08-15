"""Schemas HTTP de avances POA."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from ...evidence_management.domain.value_objects import EvidenceType
from ...indicators_capture.domain.value_objects import CaptureStatus
from ..domain.entities import PoaAdvance


class RegistrarAvanceRequest(BaseModel):
    actividad_id: int
    cuatrimestre: int = Field(ge=1, le=3)
    periodo_id: int
    programado: Decimal | None = None
    alcanzado: Decimal | None = None
    observaciones: str | None = None
    criterio_seaes_ids: set[int] = Field(default_factory=set)


class EditarAvanceRequest(BaseModel):
    programado: Decimal | None = None
    alcanzado: Decimal | None = None
    observaciones: str | None = None
    criterio_seaes_ids: set[int] | None = None


class AvanceRespuesta(BaseModel):
    id: int
    actividad_id: int
    cuatrimestre: int
    periodo_id: int
    capturista_id: int
    programado: Decimal | None
    alcanzado: Decimal | None
    observaciones: str | None
    porcentaje_cumplimiento: Decimal | None
    estado: CaptureStatus
    criterio_seaes_ids: list[int]
    advertencias: list[str]

    @classmethod
    def from_domain(cls, item: PoaAdvance) -> AvanceRespuesta:
        return cls(
            id=item.id,
            actividad_id=item.activity_id,
            cuatrimestre=item.quarter,
            periodo_id=item.period_id,
            capturista_id=item.capturer_id,
            programado=item.scheduled,
            alcanzado=item.achieved,
            observaciones=item.observations,
            porcentaje_cumplimiento=item.compliance_percentage,
            estado=item.status,
            criterio_seaes_ids=sorted(item.criteria_ids),
            advertencias=item.warnings,
        )


class AcumuladoRespuesta(BaseModel):
    disponible: bool
    actividad_id: int
    meta_anual: Decimal
    alcanzado_acumulado: Decimal
    porcentaje_meta: Decimal | None
    avances: list[AvanceRespuesta]


class VincularEvidenciaRequest(BaseModel):
    evidencia_id: int


class AdjuntarEvidenciaAvanceRequest(BaseModel):
    nombre: str = Field(min_length=1, max_length=300)
    descripcion: str = Field(min_length=1)
    fecha: date
    tipo: EvidenceType
    ruta_o_url: str = Field(min_length=1, max_length=500)
