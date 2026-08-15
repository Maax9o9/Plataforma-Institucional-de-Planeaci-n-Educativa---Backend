"""Modelo SQLAlchemy propietario de capturas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, Integer, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.db.base import Base


class CaptureModel(Base):
    __tablename__ = "capturas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    indicador_id: Mapped[int] = mapped_column(Integer, nullable=False)
    periodo_id: Mapped[int] = mapped_column(Integer, nullable=False)
    capturista_id: Mapped[int] = mapped_column(Integer, nullable=False)
    resultado: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    datos_fuente: Mapped[str | None] = mapped_column(Text)
    actividad_realizada: Mapped[str | None] = mapped_column(Text)
    observaciones: Mapped[str | None] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(
        Enum(
            "borrador",
            "enviado",
            "validado",
            "rechazado",
            name="estado_captura",
            native_enum=True,
            create_type=False,
        ),
        nullable=False,
    )
    pct_avance: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    semaforo: Mapped[str | None] = mapped_column(
        Enum(
            "verde",
            "amarillo",
            "rojo",
            name="semaforo",
            native_enum=True,
            create_type=False,
        )
    )
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
