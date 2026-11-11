"""Schemas HTTP de validacion."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from ...indicators_capture.domain.value_objects import CaptureStatus
from ..domain.entities import StateChange


class RechazarCapturaRequest(BaseModel):
    comentario: str = Field(min_length=1, max_length=1000)


class CambioEstadoRespuesta(BaseModel):
    id: int
    entidad_id: int
    de_estado: CaptureStatus | None
    a_estado: CaptureStatus
    usuario_id: int
    fecha: datetime
    comentario: str | None

    @classmethod
    def from_domain(cls, change: StateChange) -> CambioEstadoRespuesta:
        return cls(
            id=change.id,
            entidad_id=change.entity_id,
            de_estado=change.from_status,
            a_estado=change.to_status,
            usuario_id=change.user_id,
            fecha=change.created_at,
            comentario=change.comment,
        )


class PaginaCambiosEstadoRespuesta(BaseModel):
    items: list[CambioEstadoRespuesta]
    total: int
    offset: int
    limit: int
