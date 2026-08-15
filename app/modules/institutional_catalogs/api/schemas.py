"""Schemas HTTP de catalogos."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from ..domain.entities import Area, Instrument


class CrearAreaRequest(BaseModel):
    codigo: str = Field(min_length=1, max_length=30, examples=["DIP"])
    nombre: str = Field(min_length=2, max_length=150, examples=["Direccion de Planeacion"])
    area_padre_id: int | None = Field(default=None, description="Area superior opcional.")


class AreaRespuesta(BaseModel):
    id: int
    codigo: str
    nombre: str
    area_padre_id: int | None
    activo: bool

    @classmethod
    def from_domain(cls, area: Area) -> AreaRespuesta:
        return cls(
            id=area.id,
            codigo=area.code,
            nombre=area.name,
            area_padre_id=area.parent_id,
            activo=area.is_active,
        )


class ActualizarAreaRequest(BaseModel):
    codigo: str | None = Field(default=None, min_length=1, max_length=30)
    nombre: str | None = Field(default=None, min_length=2, max_length=150)
    area_padre_id: int | None = None

    @model_validator(mode="after")
    def require_one_change(self) -> ActualizarAreaRequest:
        if all(value is None for value in (self.codigo, self.nombre, self.area_padre_id)):
            raise ValueError("Debe indicar al menos un campo para actualizar.")
        return self


class CrearInstrumentoRequest(BaseModel):
    codigo: str = Field(min_length=1, max_length=30, examples=["PIDE"])
    nombre: str = Field(
        min_length=2,
        max_length=150,
        examples=["Programa Institucional de Desarrollo"],
    )
    descripcion: str | None = Field(default=None, max_length=500)


class InstrumentoRespuesta(BaseModel):
    id: int
    codigo: str
    nombre: str
    descripcion: str | None
    activo: bool

    @classmethod
    def from_domain(cls, instrument: Instrument) -> InstrumentoRespuesta:
        return cls(
            id=instrument.id,
            codigo=instrument.code,
            nombre=instrument.name,
            descripcion=instrument.description,
            activo=instrument.is_active,
        )


class ActualizarInstrumentoRequest(BaseModel):
    codigo: str | None = Field(default=None, min_length=1, max_length=30)
    nombre: str | None = Field(default=None, min_length=2, max_length=150)
    descripcion: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def require_one_change(self) -> ActualizarInstrumentoRequest:
        if all(value is None for value in (self.codigo, self.nombre, self.descripcion)):
            raise ValueError("Debe indicar al menos un campo para actualizar.")
        return self
