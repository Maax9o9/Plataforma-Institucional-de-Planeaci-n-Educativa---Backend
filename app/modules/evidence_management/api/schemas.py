"""Schemas HTTP de evidencias."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from ..domain.entities import Evidence
from ..domain.value_objects import EvidenceType, FlowEntity


class AdjuntarEvidenciaRequest(BaseModel):
    nombre: str = Field(min_length=1, max_length=300)
    descripcion: str = Field(min_length=1)
    fecha: date
    tipo: EvidenceType
    ruta_o_url: str = Field(min_length=1, max_length=500)
    entidad: FlowEntity
    entidad_id: int
    mime_type: str | None = None
    tamanio_bytes: int | None = Field(default=None, ge=0)
    checksum_sha256: str | None = Field(default=None, min_length=64, max_length=64)


class ReemplazarEvidenciaRequest(BaseModel):
    ruta_o_url: str = Field(min_length=1, max_length=500)
    mime_type: str | None = None
    tamanio_bytes: int | None = Field(default=None, ge=0)
    checksum_sha256: str | None = Field(default=None, min_length=64, max_length=64)


class EvidenciaRespuesta(BaseModel):
    id: int
    nombre: str
    descripcion: str
    fecha: date
    tipo: EvidenceType
    subida_por: int
    version_actual: VersionEvidenciaRespuesta | None = None

    @classmethod
    def from_domain(
        cls,
        evidence: Evidence,
        version_actual: VersionEvidenciaRespuesta | None = None,
    ) -> EvidenciaRespuesta:
        return cls(
            id=evidence.id,
            nombre=evidence.name,
            descripcion=evidence.description,
            fecha=evidence.evidence_date,
            tipo=evidence.evidence_type,
            subida_por=evidence.uploaded_by,
            version_actual=version_actual,
        )


class VersionEvidenciaRespuesta(BaseModel):
    numero: int
    ruta_o_url: str
    mime_type: str | None
    tamanio_bytes: int | None
    checksum_sha256: str | None
    fecha: datetime
    usuario_id: int


class PaginaVersionesEvidenciaRespuesta(BaseModel):
    items: list[VersionEvidenciaRespuesta]
    total: int
    offset: int
    limit: int
