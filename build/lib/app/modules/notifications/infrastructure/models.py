"""Modelo SQLAlchemy propietario de notifications."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.infrastructure.db.base import Base


class NotificationModel(Base):
    __tablename__ = "notificaciones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(Integer, nullable=False)
    tipo: Mapped[str] = mapped_column(String(60), nullable=False)
    correo_reservado_hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    entidad: Mapped[str | None] = mapped_column(String(60))
    entidad_id: Mapped[int | None] = mapped_column(Integer)
    titulo: Mapped[str | None] = mapped_column(String(200))
    mensaje: Mapped[str] = mapped_column(Text, nullable=False)
    leida: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enviada_por_correo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    origen_evento_id: Mapped[UUID | None] = mapped_column(nullable=True)
    aviso_id: Mapped[int | None] = mapped_column(ForeignKey("avisos.id"))
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AvisoModel(Base):
    __tablename__ = "avisos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    mensaje: Mapped[str] = mapped_column(Text, nullable=False)
    destino_ruta: Mapped[str | None] = mapped_column(String(200))
    vigente_hasta: Mapped[date | None] = mapped_column(Date)
    creado_por: Mapped[int] = mapped_column(Integer, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    adjuntos: Mapped[list[AvisoAdjuntoModel]] = relationship(
        back_populates="aviso", lazy="selectin", order_by="AvisoAdjuntoModel.id"
    )


class AvisoAdjuntoModel(Base):
    __tablename__ = "aviso_adjuntos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    aviso_id: Mapped[int] = mapped_column(ForeignKey("avisos.id"), nullable=False)
    nombre: Mapped[str] = mapped_column(String(300), nullable=False)
    ruta_o_url: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    tamanio_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)

    aviso: Mapped[AvisoModel] = relationship(back_populates="adjuntos")
