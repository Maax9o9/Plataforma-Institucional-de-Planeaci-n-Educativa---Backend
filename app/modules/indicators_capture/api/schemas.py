"""Schemas HTTP de capturas."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from ...evidence_management.domain.value_objects import EvidenceType
from ..domain.entities import Capture
from ..domain.value_objects import CaptureStatus


class RegistrarCapturaRequest(BaseModel):
    indicador_id: int
    periodo_id: int
    resultado: Decimal | None = None
    datos_fuente: str | None = None
    actividad_realizada: str | None = None
    observaciones: str | None = None


class EditarCapturaRequest(BaseModel):
    resultado: Decimal | None = None
    datos_fuente: str | None = None
    actividad_realizada: str | None = None
    observaciones: str | None = None


class AdjuntarEvidenciaCapturaRequest(BaseModel):
    nombre: str = Field(min_length=1, max_length=300)
    descripcion: str = Field(min_length=1)
    fecha: date
    tipo: EvidenceType
    ruta_o_url: str = Field(min_length=1, max_length=500)
    mime_type: str | None = None
    tamanio_bytes: int | None = Field(default=None, ge=0)
    checksum_sha256: str | None = Field(default=None, min_length=64, max_length=64)


class CapturaRespuesta(BaseModel):
    id: int
    indicador_id: int
    periodo_id: int
    capturista_id: int
    resultado: Decimal | None
    datos_fuente: str | None
    actividad_realizada: str | None
    observaciones: str | None
    estado: CaptureStatus
    porcentaje_avance: Decimal | None
    semaforo: str | None

    @classmethod
    def from_domain(cls, capture: Capture) -> CapturaRespuesta:
        return cls(
            id=capture.id,
            indicador_id=capture.indicator_id,
            periodo_id=capture.period_id,
            capturista_id=capture.capturer_id,
            resultado=capture.result,
            datos_fuente=capture.source_data,
            actividad_realizada=capture.activity,
            observaciones=capture.observations,
            estado=capture.status,
            porcentaje_avance=capture.progress_percentage,
            semaforo=capture.semaphore,
        )
