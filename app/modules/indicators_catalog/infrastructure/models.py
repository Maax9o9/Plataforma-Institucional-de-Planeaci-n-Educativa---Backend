"""Modelos SQLAlchemy propiedad de indicators_catalog."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.db.base import Base


class IndicatorModel(Base):
    __tablename__ = "indicadores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clave: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(String(300), nullable=False)
    definicion: Mapped[str | None] = mapped_column(Text)
    metodo_calculo: Mapped[str] = mapped_column(Text, nullable=False)
    unidad_medida: Mapped[str] = mapped_column(String(100), nullable=False)
    dimension: Mapped[str | None] = mapped_column(String(100))
    documento_verificacion: Mapped[str | None] = mapped_column(String(300))
    fuente_informacion: Mapped[str | None] = mapped_column(String(300))
    observaciones_metodologicas: Mapped[str | None] = mapped_column(Text)
    tipo_indicador_id: Mapped[int | None] = mapped_column(Integer)
    area_id: Mapped[int] = mapped_column(Integer, nullable=False)
    responsable_id: Mapped[int] = mapped_column(Integer, nullable=False)
    periodicidad: Mapped[str] = mapped_column(
        Enum(
            "mensual",
            "trimestral",
            "cuatrimestral",
            "anual",
            name="periodicidad",
            native_enum=True,
            create_type=False,
        ),
        nullable=False,
    )
    umbral_verde_min: Mapped[int | None] = mapped_column(SmallInteger)
    umbral_amarillo_min: Mapped[int | None] = mapped_column(SmallInteger)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class BaselineModel(Base):
    __tablename__ = "lineas_base"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    indicador_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    anio: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    periodo: Mapped[str | None] = mapped_column(String(50))
    valor: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GoalModel(Base):
    __tablename__ = "metas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    indicador_id: Mapped[int] = mapped_column(Integer, nullable=False)
    periodo_id: Mapped[int] = mapped_column(Integer, nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)


IndicatorInstrumentModel = Table(
    "indicador_instrumentos",
    Base.metadata,
    Column("indicador_id", Integer, primary_key=True),
    Column("instrumento_id", Integer, primary_key=True),
)

IndicatorCriteriaModel = Table(
    "indicador_criterios_seaes",
    Base.metadata,
    Column("indicador_id", Integer, primary_key=True),
    Column("criterio_seaes_id", Integer, primary_key=True),
)
