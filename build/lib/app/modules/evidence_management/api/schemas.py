"""Schemas HTTP de evidencias."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from ..domain.entities import Evidence
from ..domain.value_objects import EvidenceReviewStatus, EvidenceType, FlowEntity


class AdjuntarEvidenciaRequest(BaseModel):
    nombre: str = Field(min_length=1, max_length=300)
    descripcion: str = Field(min_length=1)
    fecha: date
    tipo: EvidenceType
    ruta_o_url: str = Field(min_length=1, max_length=500)
    entidad: Literal[FlowEntity.CAPTURE, FlowEntity.POA_FORM_FOLLOW_UP]
    entidad_id: int
    mime_type: str | None = None
    tamanio_bytes: int | None = Field(default=None, ge=0)
    checksum_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    #: A qué criterios del SEAES responde. Opcional: un área entrega varios
    #: archivos por cuatrimestre y no todos sirven para lo mismo, pero
    #: obligarlo lo volvería un trámite que se rellena con cualquier cosa.
    criterio_seaes_ids: list[int] = Field(default_factory=list)


class ReemplazarEvidenciaRequest(BaseModel):
    ruta_o_url: str = Field(min_length=1, max_length=500)
    mime_type: str | None = None
    tamanio_bytes: int | None = Field(default=None, ge=0)
    checksum_sha256: str | None = Field(default=None, min_length=64, max_length=64)


class DictaminarEvidenciaRequest(BaseModel):
    #: `true` aprueba, `false` rechaza. El motivo sólo se exige al rechazar.
    aprobada: bool
    comentario: str | None = None


class EvidenciaRespuesta(BaseModel):
    id: int
    nombre: str
    descripcion: str
    fecha: date
    tipo: EvidenceType
    subida_por: int
    criterio_seaes_ids: list[int] = Field(default_factory=list)
    estado_revision: EvidenceReviewStatus = EvidenceReviewStatus.PENDING
    revisado_por: int | None = None
    revisado_en: datetime | None = None
    comentario_revision: str | None = None
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
            criterio_seaes_ids=list(evidence.criteria_seaes_ids),
            estado_revision=evidence.review_status,
            revisado_por=evidence.reviewed_by,
            revisado_en=evidence.reviewed_at,
            comentario_revision=evidence.review_comment,
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
