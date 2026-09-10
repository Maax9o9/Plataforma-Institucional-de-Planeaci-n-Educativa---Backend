"""Modelo SQLAlchemy propiedad de audit."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.db.base import Base


class AuditModel(Base):
    __tablename__ = "bitacora"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(Integer)
    usuario_nombre: Mapped[str | None] = mapped_column(String(200))
    evento: Mapped[str | None] = mapped_column(String(100))
    accion: Mapped[str] = mapped_column(String(100), nullable=False)
    entidad: Mapped[str] = mapped_column(String(100), nullable=False)
    entidad_id: Mapped[int | None] = mapped_column(Integer)
    valor_anterior: Mapped[dict | None] = mapped_column(JSONB)
    valor_nuevo: Mapped[dict | None] = mapped_column(JSONB)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
