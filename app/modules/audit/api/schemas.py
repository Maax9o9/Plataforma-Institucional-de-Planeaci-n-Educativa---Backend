"""Schemas de consulta de bitacora."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from ..domain.entities import AuditEntry


class EntradaAuditoriaResponse(BaseModel):
    id: int | UUID
    evento: str
    fecha: datetime
    usuario_id: int | None
    entidad: str
    entidad_id: int | None
    accion: str
    datos: dict[str, Any]

    @classmethod
    def from_domain(cls, entry: AuditEntry) -> EntradaAuditoriaResponse:
        return cls(
            id=entry.id,
            evento=entry.event_name,
            fecha=entry.occurred_at,
            usuario_id=entry.actor_id,
            entidad=entry.aggregate_type,
            entidad_id=entry.aggregate_id,
            accion=entry.action,
            datos=entry.data,
        )


class PaginaAuditoriaResponse(BaseModel):
    items: list[EntradaAuditoriaResponse]
    total: int
    offset: int
    limit: int
