"""Modelo SQLAlchemy propiedad de periods."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, Integer, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.db.base import Base


class PeriodModel(Base):
    __tablename__ = "periodos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tipo: Mapped[str] = mapped_column(
        Enum("indicadores", "poa", name="tipo_periodo", native_enum=True, create_type=False),
        nullable=False,
    )
    periodicidad: Mapped[str | None] = mapped_column(
        Enum(
            "mensual",
            "trimestral",
            "cuatrimestral",
            "anual",
            name="periodicidad",
            native_enum=True,
            create_type=False,
        )
    )
    anio: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    etiqueta: Mapped[str] = mapped_column(String(100), nullable=False)
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_limite: Mapped[date] = mapped_column(Date, nullable=False)
    estado: Mapped[str] = mapped_column(
        Enum(
            "borrador",
            "abierto",
            "cerrado",
            name="estado_periodo",
            native_enum=True,
            create_type=False,
        ),
        nullable=False,
    )
    motivo_reapertura: Mapped[str | None] = mapped_column(Text)
    reabierto_por: Mapped[int | None] = mapped_column(Integer)
    reabierto_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
