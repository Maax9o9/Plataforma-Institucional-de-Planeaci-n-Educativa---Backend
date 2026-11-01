from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, Numeric, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.db.base import Base

from ..domain.entities import DECIMALES_DE_LA_META, ENTEROS_DE_LA_META

PRECISION_DE_LA_META = Numeric(ENTEROS_DE_LA_META + DECIMALES_DE_LA_META, DECIMALES_DE_LA_META)


class PoaAreaModel(Base):
    __tablename__ = "poa_inst_areas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ejercicio_id: Mapped[int] = mapped_column(Integer, nullable=False)
    area_id: Mapped[int] = mapped_column(Integer, nullable=False)
    estado: Mapped[str] = mapped_column(String(30), nullable=False, default="borrador")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PoaActivityModel(Base):
    __tablename__ = "poa_inst_actividades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    poa_area_id: Mapped[int] = mapped_column(Integer, nullable=False)
    nodo_id: Mapped[int | None] = mapped_column(Integer)
    denominacion: Mapped[str] = mapped_column(Text, nullable=False)
    unidad_medida_id: Mapped[int | None] = mapped_column(Integer)
    metodo_evaluacion: Mapped[str | None] = mapped_column(Text)
    meta_anual: Mapped[Decimal | None] = mapped_column(PRECISION_DE_LA_META)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class MonthlyScheduleModel(Base):
    __tablename__ = "poa_inst_programacion_mensual"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actividad_id: Mapped[int] = mapped_column(Integer, nullable=False)
    mes: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    meta: Mapped[Decimal] = mapped_column(PRECISION_DE_LA_META, nullable=False)
    incluido: Mapped[bool] = mapped_column(Boolean, nullable=False)
