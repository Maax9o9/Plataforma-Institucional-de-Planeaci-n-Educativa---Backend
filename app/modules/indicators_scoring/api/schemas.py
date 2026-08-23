"""Schemas HTTP de semaforizacion."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, model_validator

from app.core.types import InstitutionalDecimal, PercentageDecimal

from ..domain.strategies import Thresholds


class UmbralesSemaforoRequest(BaseModel):
    umbral_verde_min: int = Field(ge=0, le=100, examples=[90])
    umbral_amarillo_min: int = Field(ge=0, le=100, examples=[40])


class UmbralesSemaforoRespuesta(BaseModel):
    umbral_verde_min: int
    umbral_amarillo_min: int

    @classmethod
    def from_domain(cls, thresholds: Thresholds) -> UmbralesSemaforoRespuesta:
        return cls(
            umbral_verde_min=thresholds.green,
            umbral_amarillo_min=thresholds.yellow,
        )


class UmbralesPersonalizadosRequest(BaseModel):
    umbral_verde_min: int | None = Field(default=None, ge=0, le=100)
    umbral_amarillo_min: int | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def validate_pair(self) -> UmbralesPersonalizadosRequest:
        if (self.umbral_verde_min is None) != (self.umbral_amarillo_min is None):
            raise ValueError("Los dos umbrales deben enviarse juntos o ambos ser nulos.")
        if (
            self.umbral_verde_min is not None
            and self.umbral_amarillo_min is not None
            and self.umbral_amarillo_min >= self.umbral_verde_min
        ):
            raise ValueError("El umbral amarillo debe ser menor que el verde.")
        return self


class TendenciaPuntoRespuesta(BaseModel):
    periodo_id: int
    periodo_etiqueta: str
    fecha_inicio: date
    resultado: InstitutionalDecimal | None
    meta: InstitutionalDecimal | None
    porcentaje_avance: PercentageDecimal | None
    semaforo: str | None
