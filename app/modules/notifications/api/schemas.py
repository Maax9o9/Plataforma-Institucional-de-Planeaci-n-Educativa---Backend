from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.modules.institutional_catalogs.domain.strategic_tree_entities import (
    MAYOR_ENTERO_DE_LA_BASE,
)

from ..application.area_notices import LARGO_DEL_MENSAJE, LARGO_DEL_TITULO, AvisoEntregado

IdDeLaBase = Annotated[int, Field(ge=1, le=MAYOR_ENTERO_DE_LA_BASE)]
TituloDelAviso = Annotated[str, Field(min_length=1, max_length=LARGO_DEL_TITULO)]
MensajeDelAviso = Annotated[str, Field(min_length=1, max_length=LARGO_DEL_MENSAJE)]


class NotificacionRespuesta(BaseModel):
    id: int
    tipo: str
    titulo: str | None = Field(max_length=LARGO_DEL_TITULO)
    mensaje: str
    entidad: str | None
    entidad_id: int | None
    leida: bool
    enviada_por_correo: bool
    fecha: datetime

    @classmethod
    def from_domain(cls, notificacion) -> NotificacionRespuesta:
        return cls(
            id=notificacion.id,
            tipo=notificacion.notification_type,
            titulo=notificacion.title,
            mensaje=notificacion.message,
            entidad=notificacion.entity,
            entidad_id=notificacion.entity_id,
            leida=notificacion.read,
            enviada_por_correo=notificacion.sent_by_email,
            fecha=notificacion.created_at,
        )


class AvisoDePlaneacionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    areas: Annotated[list[IdDeLaBase], Field(min_length=1)] | None
    titulo: TituloDelAviso
    mensaje: MensajeDelAviso


class AvisoPorAreaRespuesta(BaseModel):
    area_id: int
    area: str | None
    personas: int

    @classmethod
    def from_domain(cls, entregado: AvisoEntregado) -> AvisoPorAreaRespuesta:
        return cls(area_id=entregado.area_id, area=entregado.area, personas=entregado.personas)


class AvisoEntregadoRespuesta(BaseModel):
    entregados: int
    areas: list[AvisoPorAreaRespuesta]

    @classmethod
    def from_domain(cls, entregados: list[AvisoEntregado]) -> AvisoEntregadoRespuesta:
        return cls(
            entregados=sum(uno.personas for uno in entregados),
            areas=[AvisoPorAreaRespuesta.from_domain(uno) for uno in entregados],
        )
