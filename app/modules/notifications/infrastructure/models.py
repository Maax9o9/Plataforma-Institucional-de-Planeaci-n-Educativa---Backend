"""Modelo SQLAlchemy propietario de notifications."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.db.base import Base


class NotificationModel(Base):
    __tablename__ = "notificaciones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(Integer, nullable=False)
    tipo: Mapped[str] = mapped_column(
        Enum(
            "apertura_periodo",
            "validacion",
            "rechazo",
            "recordatorio_5d",
            "recordatorio_3d",
            "recordatorio_2d",
            "recordatorio_1d",
            name="tipo_notificacion",
            native_enum=True,
            create_type=False,
        ),
        nullable=False,
    )
    entidad: Mapped[str | None] = mapped_column(String(30))
    entidad_id: Mapped[int | None] = mapped_column(Integer)
    mensaje: Mapped[str] = mapped_column(Text, nullable=False)
    leida: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enviada_por_correo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    origen_evento_id: Mapped[UUID | None] = mapped_column(nullable=True)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
