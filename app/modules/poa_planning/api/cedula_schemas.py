"""Contrato HTTP de la cédula institucional POA."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.types import NonNegativeInstitutionalDecimal, PercentageDecimal


class PoaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


StrategyType = Literal["Eficiencia", "Eficacia", "Pertinencia", "Vinculación", "Equidad de Género"]


class FirmantePoaSchema(PoaRequest):
    nombre: str = Field(min_length=1, max_length=200)
    cargo: str = Field(min_length=1, max_length=200)


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


class CuatrimestreCedulaRequest(PoaRequest):
    numero: int = Field(ge=1, le=3)
    fecha_inicio: date
    fecha_fin: date


class CuatrimestreCedulaRespuesta(CuatrimestreCedulaRequest):
    periodo_id: int


class CrearCedulaPoaRequest(PoaRequest):
    ejercicio_id: int
    estrategia_clave: str = Field(min_length=3, max_length=20, examples=["6.1"])
    area_responsable_id: int
    tipo_estrategia: StrategyType | None = None
    firmantes: list[FirmantePoaSchema] = Field(default_factory=list, max_length=2)
    alcance_efecto_socioeconomico: str | None = None
    cuatrimestres: list[CuatrimestreCedulaRequest] = Field(min_length=3, max_length=3)

    @field_validator("firmantes")
    @classmethod
    def validate_signatory_count(cls, value):
        if value is not None and len(value) not in {0, 2}:
            raise ValueError("Indique exactamente dos firmantes o deje la lista vacía.")
        return value


class CedulaPoaRespuesta(BaseModel):
    id: int
    ejercicio_id: int
    objetivo_numero: int
    estrategia_clave: str
    area_responsable_id: int
    tipo_estrategia: str | None
    firmantes: list[FirmantePoaSchema]
    alcance_efecto_socioeconomico: str | None
    creado_por: int
    version: int
    creado_en: datetime
    actualizado_en: datetime
    cuatrimestres: list[CuatrimestreCedulaRespuesta]


class ActualizarCedulaPoaRequest(PoaRequest):
    tipo_estrategia: StrategyType | None = None
    firmantes: list[FirmantePoaSchema] | None = Field(default=None, max_length=2)
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
                self.tipo_estrategia,
                self.firmantes,
            )
        ):
            raise ValueError("Debe indicar al menos un campo para actualizar.")
        return self

    @field_validator("firmantes")
    @classmethod
    def validate_signatory_count(cls, value):
        if value is not None and len(value) not in {0, 2}:
            raise ValueError("Indique exactamente dos firmantes o deje la lista vacía.")
        return value


class AgregarIndicadorCedulaRequest(PoaRequest):
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


class ActualizarIndicadorCedulaRequest(PoaRequest):
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


class CapturarTotalIndicadorRequest(PoaRequest):
    periodo_id: int
    total_alcanzado: NonNegativeInstitutionalDecimal
    porcentaje_alcanzado: NonNegativeInstitutionalDecimal


class AgregarActividadCedulaRequest(PoaRequest):
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
    actividad_upe: str | None = Field(
        default=None,
        description="Qué significa la actividad en concreto para el área que la ejecuta.",
    )
    criterio_seaes_ids: list[int] = Field(default_factory=list)


class AsignarCriteriosSeaesRequest(BaseModel):
    criterio_seaes_ids: list[int] = Field(
        default_factory=list,
        description=(
            "Criterios que clasifican la actividad. SEAES admite varios por "
            "actividad; una lista vacía los retira todos."
        ),
    )


class ActualizarActividadCedulaRequest(PoaRequest):
    unidad_medida: str | None = Field(default=None, min_length=1, max_length=100)
    meta_anual: NonNegativeInstitutionalDecimal | None = None
    area_ejecutora_id: int | None = None
    observaciones: str | None = None
    actividad_upe: str | None = None

    @model_validator(mode="after")
    def require_change(self):
        if all(
            value is None
            for value in (
                self.unidad_medida,
                self.meta_anual,
                self.area_ejecutora_id,
                self.observaciones,
                self.actividad_upe,
            )
        ):
            raise ValueError("Debe indicar al menos un campo para actualizar.")
        return self


class RegistrarSeguimientoCedulaRequest(PoaRequest):
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


class ActualizarJustificacionSeguimientoRequest(PoaRequest):
    justificacion_desviacion: str = Field(min_length=1)


class CedulaPoaDetalleRespuesta(CedulaPoaRespuesta):
    anio: int
    titulo: str
    institucion: str
    formato: str
    estrategia_numero: int
    objetivo_denominacion: str
    estrategia_denominacion: str
    indicadores: list[IndicadorCedulaRespuesta]
    actividades: list[ActividadCedulaRespuesta]
    seguimientos: list[SeguimientoCedulaRespuesta]


class EmitirCedulaPoaRequest(PoaRequest):
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


class ActividadTarjetaRespuesta(BaseModel):
    id: int
    clave: str
    descripcion: str
    unidad_medida: str
    meta_anual: Decimal


class SeguimientoTarjetaRespuesta(BaseModel):
    id: int
    cedula_id: int
    actividad: ActividadTarjetaRespuesta
    area_ejecutora_id: int | None
    criterio_seaes_ids: list[int]
    cuatrimestre: int
    periodo_id: int
    programado: Decimal
    alcanzado: Decimal | None
    justificacion_desviacion: str | None
    progreso: str | None
    alcance: str | None
    estado: str
    comentario_revision: str | None
    evidencias: int
    actualizado_en: datetime


class PaginaSeguimientosRespuesta(BaseModel):
    items: list[SeguimientoTarjetaRespuesta]
    total: int
    offset: int
    limit: int
