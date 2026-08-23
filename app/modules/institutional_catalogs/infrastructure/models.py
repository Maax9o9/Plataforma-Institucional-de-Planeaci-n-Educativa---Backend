"""Modelos SQLAlchemy propiedad de institutional_catalogs."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.db.base import Base


class AreaModel(Base):
    __tablename__ = "areas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    codigo: Mapped[str | None] = mapped_column(String(30), unique=True)
    parent_id: Mapped[int | None] = mapped_column(Integer)
    tipo: Mapped[str] = mapped_column(String(30), nullable=False, default="administrativa")
    color: Mapped[str | None] = mapped_column(String(7))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class InstrumentModel(Base):
    __tablename__ = "instrumentos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    codigo: Mapped[str | None] = mapped_column(String(30), unique=True)
    descripcion: Mapped[str | None] = mapped_column(String(500))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class CriteriaSeaesModel(Base):
    __tablename__ = "criterios_seaes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clave: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(String(300), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class IndicatorTypeModel(Base):
    __tablename__ = "tipos_indicador"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class SystemConfigModel(Base):
    __tablename__ = "config_sistema"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    umbral_verde_min: Mapped[int] = mapped_column(Integer, nullable=False)
    umbral_amarillo_min: Mapped[int] = mapped_column(Integer, nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_por: Mapped[int | None] = mapped_column(Integer)
