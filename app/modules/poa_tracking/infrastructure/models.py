"""Modelo SQLAlchemy propietario de poa_tracking."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Column, DateTime, Enum, Integer, Numeric, SmallInteger, Table, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.db.base import Base


class PoaAdvanceModel(Base):
    __tablename__ = "poa_avances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actividad_id: Mapped[int] = mapped_column(Integer, nullable=False)
    cuatrimestre: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    periodo_id: Mapped[int] = mapped_column(Integer, nullable=False)
    capturista_id: Mapped[int] = mapped_column(Integer, nullable=False)
    programado: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    alcanzado: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    observaciones: Mapped[str | None] = mapped_column(Text)
    pct_cumplimiento: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
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
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


PoaAdvanceCriteriaModel = Table(
    "poa_avance_criterios_seaes",
    Base.metadata,
    Column("poa_avance_id", Integer, primary_key=True),
    Column("criterio_seaes_id", Integer, primary_key=True),
)
