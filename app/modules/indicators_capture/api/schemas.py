"""Schemas HTTP de capturas."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.core.types import InstitutionalDecimal, PercentageDecimal

from ...evidence_management.domain.value_objects import EvidenceType
from ..domain.entities import Capture
from ..domain.value_objects import CaptureStatus


class RegistrarCapturaRequest(BaseModel):
    indicador_id: int
    periodo_id: int
    resultado: InstitutionalDecimal | None = None
    datos_fuente: str | None = None
    actividad_realizada: str | None = None
    observaciones: str | None = None


class EditarCapturaRequest(BaseModel):
    version: int | None = Field(default=None, ge=1)
    resultado: InstitutionalDecimal | None = None
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
    resultado: InstitutionalDecimal | None
    datos_fuente: str | None
    actividad_realizada: str | None
    observaciones: str | None
    estado: CaptureStatus
    porcentaje_avance: PercentageDecimal | None
    semaforo: str | None
    creado_en: datetime
    actualizado_en: datetime
    version: int

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
            creado_en=capture.created_at,
            actualizado_en=capture.updated_at,
            version=capture.version,
        )


class IndicadorCapturaResumen(BaseModel):
    id: int
    clave: str
    nombre: str
    unidad_medida: str


class PeriodoCapturaResumen(BaseModel):
    id: int
    etiqueta: str
    estado: str
    fecha_limite: date


class AreaCapturaResumen(BaseModel):
    id: int
    codigo: str
    nombre: str
    color: str | None


class CapturistaResumen(BaseModel):
    id: int
    nombre: str
    correo: str


class CapturaBandejaRespuesta(BaseModel):
    id: int
    indicador: IndicadorCapturaResumen
    periodo: PeriodoCapturaResumen
    area: AreaCapturaResumen
    capturista: CapturistaResumen
    resultado: InstitutionalDecimal | None
    meta: InstitutionalDecimal | None
    porcentaje_avance: PercentageDecimal | None
    semaforo: str | None
    estado: CaptureStatus
    evidencias_total: int
    actualizado_en: datetime

    @classmethod
    def from_row(cls, row) -> CapturaBandejaRespuesta:
        return cls(
            id=row.id,
            indicador=IndicadorCapturaResumen(
                id=row.indicator_id,
                clave=row.indicator_key,
                nombre=row.indicator_name,
                unidad_medida=row.indicator_unit,
            ),
            periodo=PeriodoCapturaResumen(
                id=row.period_id,
                etiqueta=row.period_label,
                estado=row.period_status,
                fecha_limite=row.period_deadline,
            ),
            area=AreaCapturaResumen(
                id=row.area_id,
                codigo=row.area_code,
                nombre=row.area_name,
                color=row.area_color,
            ),
            capturista=CapturistaResumen(
                id=row.capturer_id,
                nombre=row.capturer_name,
                correo=row.capturer_email,
            ),
            resultado=row.result,
            meta=row.goal,
            porcentaje_avance=row.progress_percentage,
            semaforo=row.semaphore,
            estado=CaptureStatus(row.status),
            evidencias_total=row.evidence_total,
            actualizado_en=row.updated_at,
        )


class PaginaCapturasRespuesta(BaseModel):
    items: list[CapturaBandejaRespuesta]
    total: int
    offset: int
    limit: int


class IndicadorPendienteRespuesta(BaseModel):
    id: int
    clave: str
    nombre: str
    unidad_medida: str


class PeriodoPendienteRespuesta(BaseModel):
    id: int
    etiqueta: str
    fecha_limite: date
    estado: str


class CapturaPendienteRespuesta(BaseModel):
    indicador: IndicadorPendienteRespuesta
    periodo: PeriodoPendienteRespuesta
    meta: InstitutionalDecimal | None
    captura: CapturaRespuesta | None
    evidencias_total: int


class PaginaPendientesRespuesta(BaseModel):
    items: list[CapturaPendienteRespuesta]
    total: int
    offset: int
    limit: int
