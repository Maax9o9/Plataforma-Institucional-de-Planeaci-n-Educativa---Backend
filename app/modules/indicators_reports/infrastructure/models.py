"""Modelo SQLAlchemy de log de reportes."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.db.base import Base


class ReportLogModel(Base):
    __tablename__ = "reportes_generados"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(Integer, nullable=False)
    tipo: Mapped[str] = mapped_column(String(100), nullable=False)
    parametros: Mapped[dict | None] = mapped_column(JSON)
    formato: Mapped[str] = mapped_column(String(20), nullable=False)
    ruta_o_url: Mapped[str | None] = mapped_column(String(500))
    generado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
