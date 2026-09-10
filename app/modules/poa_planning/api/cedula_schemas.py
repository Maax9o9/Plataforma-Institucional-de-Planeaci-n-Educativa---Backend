"""Contrato HTTP de la cédula institucional POA."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.core.types import NonNegativeInstitutionalDecimal, PercentageDecimal


class ObjetivoPoaCatalogoRespuesta(BaseModel):
    clave: str
    numero: int
    denominacion: str
    activo: bool


class EstrategiaPoaCatalogoRespuesta(BaseModel):
    clave: str
    objetivo_numero: int
    denominacion: str
    activo: bool


class IndicadorPoaCatalogoRespuesta(BaseModel):
    clave: str
    objetivo_numero: int
    nombre: str
    formula: str
    unidad_medida: str
    activo: bool


class ActividadPoaCatalogoRespuesta(BaseModel):
    clave: str
    estrategia_clave: str
    descripcion: str
    activo: bool


class CuatrimestreCedulaRequest(BaseModel):
    numero: int = Field(ge=1, le=3)
    fecha_inicio: date
    fecha_fin: date


class CuatrimestreCedulaRespuesta(CuatrimestreCedulaRequest):
    periodo_id: int


class CrearCedulaPoaRequest(BaseModel):
    ejercicio_id: int
    estrategia_clave: str = Field(min_length=3, max_length=20, examples=["6.1"])
    area_responsable_id: int
    alcance_efecto_socioeconomico: str | None = None
    cuatrimestres: list[CuatrimestreCedulaRequest] = Field(min_length=3, max_length=3)


class CedulaPoaRespuesta(BaseModel):
    id: int
    ejercicio_id: int
    objetivo_numero: int
    estrategia_clave: str
    area_responsable_id: int
    alcance_efecto_socioeconomico: str | None
    creado_por: int
    version: int
    creado_en: datetime
    actualizado_en: datetime
    cuatrimestres: list[CuatrimestreCedulaRespuesta]


class ActualizarCedulaPoaRequest(BaseModel):
    estrategia_clave: str | None = Field(default=None, min_length=3, max_length=20)
    area_responsable_id: int | None = None
    alcance_efecto_socioeconomico: str | None = None

    @model_validator(mode="after")
    def require_change(self):
        if all(
            value is None
            for value in (
                self.estrategia_clave,
                self.area_responsable_id,
                self.alcance_efecto_socioeconomico,
            )
        ):
            raise ValueError("Debe indicar al menos un campo para actualizar.")
        return self


class AgregarIndicadorCedulaRequest(BaseModel):
    indicador_clave: str = Field(min_length=2, max_length=30)
    meta_institucional: NonNegativeInstitutionalDecimal | None = None
    linea_base_anio: int | None = Field(default=None, ge=2000, le=2200)
    linea_base_valor: NonNegativeInstitutionalDecimal | None = None
    porcentaje_actual: PercentageDecimal | None = Field(default=None, ge=0, le=100)
    numero_a_lograr: NonNegativeInstitutionalDecimal | None = None
    porcentaje_a_lograr: PercentageDecimal | None = Field(default=None, ge=0, le=100)


class IndicadorCedulaRespuesta(BaseModel):
    id: int
    cedula_id: int
    indicador_clave: str
    nombre: str
    formula: str
    unidad_medida: str
    meta_institucional: Decimal | None
    linea_base_anio: int | None
    linea_base_valor: Decimal | None
    porcentaje_actual: Decimal | None
    numero_a_lograr: Decimal | None
    porcentaje_a_lograr: Decimal | None
    total_alcanzado: Decimal | None
    porcentaje_alcanzado: Decimal | None


class ActualizarIndicadorCedulaRequest(BaseModel):
    meta_institucional: NonNegativeInstitutionalDecimal | None = None
    linea_base_anio: int | None = Field(default=None, ge=2000, le=2200)
    linea_base_valor: NonNegativeInstitutionalDecimal | None = None
    porcentaje_actual: PercentageDecimal | None = Field(default=None, ge=0, le=100)
    numero_a_lograr: NonNegativeInstitutionalDecimal | None = None
    porcentaje_a_lograr: PercentageDecimal | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def require_change(self):
        if all(
            value is None
            for value in (
                self.meta_institucional,
                self.linea_base_anio,
                self.linea_base_valor,
                self.porcentaje_actual,
                self.numero_a_lograr,
                self.porcentaje_a_lograr,
            )
        ):
            raise ValueError("Debe indicar al menos un campo para actualizar.")
        return self


class CapturarTotalIndicadorRequest(BaseModel):
    periodo_id: int
    total_alcanzado: NonNegativeInstitutionalDecimal
    porcentaje_alcanzado: NonNegativeInstitutionalDecimal | None = None


class AgregarActividadCedulaRequest(BaseModel):
    actividad_clave: str = Field(min_length=5, max_length=30)
    unidad_medida: str = Field(min_length=1, max_length=100)
    meta_anual: NonNegativeInstitutionalDecimal
    area_ejecutora_id: int | None = None
    observaciones: str | None = None


class ActividadCedulaRespuesta(BaseModel):
    id: int
    cedula_id: int
    actividad_clave: str
    descripcion: str
    unidad_medida: str
    meta_anual: Decimal
    area_ejecutora_id: int | None
    observaciones: str | None


class ActualizarActividadCedulaRequest(BaseModel):
    unidad_medida: str | None = Field(default=None, min_length=1, max_length=100)
    meta_anual: NonNegativeInstitutionalDecimal | None = None
    area_ejecutora_id: int | None = None
    observaciones: str | None = None

    @model_validator(mode="after")
    def require_change(self):
        if all(
            value is None
            for value in (
                self.unidad_medida,
                self.meta_anual,
                self.area_ejecutora_id,
                self.observaciones,
            )
        ):
            raise ValueError("Debe indicar al menos un campo para actualizar.")
        return self


class RegistrarSeguimientoCedulaRequest(BaseModel):
    periodo_id: int
    programado: NonNegativeInstitutionalDecimal
    alcanzado: NonNegativeInstitutionalDecimal | None = None
    justificacion_desviacion: str | None = None
    progreso: str | None = None
    alcance: str | None = None


class SeguimientoCedulaRespuesta(BaseModel):
    id: int
    cedula_actividad_id: int
    cuatrimestre: int
    periodo_id: int
    capturado_por: int
    programado: Decimal
    programado_porcentaje: Decimal | None
    alcanzado: Decimal | None
    alcanzado_porcentaje: Decimal | None
    justificacion_desviacion: str | None
    progreso: str | None
    alcance: str | None
    estado: str
    comentario_revision: str | None


class ActualizarJustificacionSeguimientoRequest(BaseModel):
    justificacion_desviacion: str = Field(min_length=1)


class CedulaPoaDetalleRespuesta(CedulaPoaRespuesta):
    objetivo_denominacion: str
    estrategia_denominacion: str
    indicadores: list[IndicadorCedulaRespuesta]
    actividades: list[ActividadCedulaRespuesta]
    seguimientos: list[SeguimientoCedulaRespuesta]


class EmitirCedulaPoaRequest(BaseModel):
    cuatrimestre: int = Field(ge=1, le=3)
    periodo_id: int


class EmisionCedulaPoaRespuesta(BaseModel):
    id: int
    cedula_id: int
    cuatrimestre: int
    periodo_id: int
    nombre: str
    snapshot: dict[str, Any]
    emitido_por: int
    emitido_en: datetime


class RechazarSeguimientoRequest(BaseModel):
    comentario: str = Field(
        min_length=1,
        description="Obligatorio: el area debe saber qué corregir.",
    )


class CambioEstadoSeguimientoRespuesta(BaseModel):
    id: int
    seguimiento_id: int
    de_estado: str | None
    a_estado: str
    usuario_id: int
    fecha: datetime
    comentario: str | None


class PaginaHistorialSeguimientoRespuesta(BaseModel):
    items: list[CambioEstadoSeguimientoRespuesta]
    total: int
    offset: int
    limit: int
