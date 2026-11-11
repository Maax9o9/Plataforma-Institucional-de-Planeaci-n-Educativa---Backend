"""Entidad de notificaciones internas."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from app.shared.domain.base_entity import BaseEntity


@dataclass(kw_only=True)
class Notification(BaseEntity):
    user_id: int
    notification_type: str
    message: str
    title: str | None = None
    entity: str | None = None
    entity_id: int | None = None
    read: bool = False
    sent_by_email: bool = False
    source_event_id: UUID | None = None
    aviso_id: int | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class AvisoAdjunto:
    nombre: str
    ruta_o_url: str
    mime_type: str
    tamanio_bytes: int
    id: int = 0


@dataclass
class Aviso:
    titulo: str
    mensaje: str
    creado_por: int
    destino_ruta: str | None = None
    vigente_hasta: date | None = None
    adjuntos: tuple[AvisoAdjunto, ...] = ()
    id: int = 0
    creado_en: datetime | None = None

    def vigente_el(self, dia: date) -> bool:
        return self.vigente_hasta is None or self.vigente_hasta >= dia


@dataclass(frozen=True)
class EntregaDelAviso:
    aviso_id: int
    usuario_id: int
    leida: bool


@dataclass(frozen=True)
class LecturaPorArea:
    area_id: int | None
    area: str | None
    entregados: int
    leidos: int


@dataclass(frozen=True)
class AvisoConSusCifras:
    aviso: Aviso
    entregados: int
    leidos: int
    por_area: tuple[LecturaPorArea, ...] = ()
