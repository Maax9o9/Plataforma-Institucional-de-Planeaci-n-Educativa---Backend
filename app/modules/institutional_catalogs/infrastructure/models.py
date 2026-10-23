"""Modelos SQLAlchemy propiedad de institutional_catalogs."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Integer, String, Text
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


class InstrumentVersionModel(Base):
    """Cada edición de un instrumento; el árbol cuelga de una versión.

    Las restricciones (la etiqueta única por instrumento, las foráneas) viven en
    la migración 0038 y no se repiten aquí.
    """

    __tablename__ = "instrumento_versiones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrumento_id: Mapped[int] = mapped_column(Integer, nullable=False)
    etiqueta: Mapped[str] = mapped_column(String(120), nullable=False)
    vigente_desde: Mapped[date] = mapped_column(Date, nullable=False)
    #: NULL mientras la versión está en borrador.
    publicada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StrategicNodeModel(Base):
    """Un nodo del árbol de una versión, con su padre explícito.

    `tipo` guarda el valor de `NodeKind`; el `CHECK`, la `UNIQUE` entre hermanos
    y la foránea compuesta del padre viven en la migración 0038.
    """

    __tablename__ = "nodos_estrategicos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(Integer, nullable=False)
    padre_id: Mapped[int | None] = mapped_column(Integer)
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    clave: Mapped[str] = mapped_column(String(50), nullable=False)
    denominacion: Mapped[str] = mapped_column(Text, nullable=False)
    orden: Mapped[int] = mapped_column(Integer, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class CriteriaSeaesModel(Base):
    __tablename__ = "criterios_seaes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clave: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(String(300), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class UnitOfMeasureModel(Base):
    __tablename__ = "unidades_medida"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clave: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    plural: Mapped[str] = mapped_column(String(100), nullable=False)
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
