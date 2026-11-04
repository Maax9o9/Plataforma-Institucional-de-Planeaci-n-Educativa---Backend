from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.modules.institutional_catalogs.domain.strategic_tree_entities import (
    MAYOR_ENTERO_DE_LA_BASE,
)

from ..application.area_notices import (
    CUANTOS_ADJUNTOS_CABEN,
    LARGO_DEL_DESTINO,
    LARGO_DEL_MENSAJE,
    LARGO_DEL_NOMBRE_DEL_ADJUNTO,
    LARGO_DEL_TITULO,
    AdjuntoPedido,
    AvisoEntregado,
    AvisoRedactado,
)
from ..application.avisos_consultados import EntregaConSuAviso
from ..domain.entities import AvisoAdjunto, AvisoConSusCifras, LecturaPorArea

IdDeLaBase = Annotated[int, Field(ge=1, le=MAYOR_ENTERO_DE_LA_BASE)]
TituloDelAviso = Annotated[str, Field(min_length=1, max_length=LARGO_DEL_TITULO)]
MensajeDelAviso = Annotated[str, Field(min_length=1, max_length=LARGO_DEL_MENSAJE)]
DestinoDelAviso = Annotated[str, Field(min_length=1, max_length=LARGO_DEL_DESTINO)]
NombreDelAdjunto = Annotated[str, Field(min_length=1, max_length=LARGO_DEL_NOMBRE_DEL_ADJUNTO)]
RutaDelAdjunto = Annotated[str, Field(min_length=1, max_length=500)]


class AdjuntoRespuesta(BaseModel):
    nombre: str
    ruta_o_url: str
    mime_type: str
    tamanio_bytes: int

    @classmethod
    def from_domain(cls, adjunto: AvisoAdjunto) -> AdjuntoRespuesta:
        return cls(
            nombre=adjunto.nombre,
            ruta_o_url=adjunto.ruta_o_url,
            mime_type=adjunto.mime_type,
            tamanio_bytes=adjunto.tamanio_bytes,
        )


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
    aviso_id: int | None
    destino_ruta: str | None
    vigente_hasta: date | None
    adjuntos: list[AdjuntoRespuesta]

    @classmethod
    def from_domain(cls, entrega: EntregaConSuAviso) -> NotificacionRespuesta:
        notificacion = entrega.entrega
        aviso = entrega.aviso
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
            aviso_id=notificacion.aviso_id,
            destino_ruta=None if aviso is None else aviso.destino_ruta,
            vigente_hasta=None if aviso is None else aviso.vigente_hasta,
            adjuntos=(
                []
                if aviso is None
                else [AdjuntoRespuesta.from_domain(uno) for uno in aviso.adjuntos]
            ),
        )


class AdjuntoDelAvisoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: NombreDelAdjunto
    ruta: RutaDelAdjunto


LosAdjuntosDelAviso = Annotated[
    list[AdjuntoDelAvisoRequest], Field(max_length=CUANTOS_ADJUNTOS_CABEN)
]


class AvisoDePlaneacionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    areas: Annotated[list[IdDeLaBase], Field(min_length=1)] | None
    titulo: TituloDelAviso
    mensaje: MensajeDelAviso
    destino_ruta: DestinoDelAviso | None = None
    vigente_hasta: date | None = None
    adjuntos: LosAdjuntosDelAviso = []

    def los_adjuntos(self) -> list[AdjuntoPedido]:
        return [AdjuntoPedido(nombre=uno.nombre, ruta=uno.ruta) for uno in self.adjuntos]


class AvisoPorAreaRespuesta(BaseModel):
    area_id: int
    area: str | None
    personas: int

    @classmethod
    def from_domain(cls, entregado: AvisoEntregado) -> AvisoPorAreaRespuesta:
        return cls(area_id=entregado.area_id, area=entregado.area, personas=entregado.personas)


class AvisoEntregadoRespuesta(BaseModel):
    aviso_id: int
    entregados: int
    areas: list[AvisoPorAreaRespuesta]

    @classmethod
    def from_domain(cls, redactado: AvisoRedactado) -> AvisoEntregadoRespuesta:
        return cls(
            aviso_id=redactado.aviso_id,
            entregados=sum(uno.personas for uno in redactado.entregados),
            areas=[AvisoPorAreaRespuesta.from_domain(uno) for uno in redactado.entregados],
        )


class LecturaPorAreaRespuesta(BaseModel):
    area_id: int | None
    area: str | None
    entregados: int
    leidos: int

    @classmethod
    def from_domain(cls, lectura: LecturaPorArea) -> LecturaPorAreaRespuesta:
        return cls(
            area_id=lectura.area_id,
            area=lectura.area,
            entregados=lectura.entregados,
            leidos=lectura.leidos,
        )


class AvisoRedactadoRespuesta(BaseModel):
    id: int
    titulo: str
    mensaje: str
    destino_ruta: str | None
    vigente_hasta: date | None
    creado_por: int
    creado_en: datetime
    adjuntos: list[AdjuntoRespuesta]
    entregados: int
    leidos: int
    por_area: list[LecturaPorAreaRespuesta]

    @classmethod
    def from_domain(cls, cifras: AvisoConSusCifras) -> AvisoRedactadoRespuesta:
        aviso = cifras.aviso
        return cls(
            id=aviso.id,
            titulo=aviso.titulo,
            mensaje=aviso.mensaje,
            destino_ruta=aviso.destino_ruta,
            vigente_hasta=aviso.vigente_hasta,
            creado_por=aviso.creado_por,
            creado_en=aviso.creado_en,
            adjuntos=[AdjuntoRespuesta.from_domain(uno) for uno in aviso.adjuntos],
            entregados=cifras.entregados,
            leidos=cifras.leidos,
            por_area=[LecturaPorAreaRespuesta.from_domain(uno) for uno in cifras.por_area],
        )
