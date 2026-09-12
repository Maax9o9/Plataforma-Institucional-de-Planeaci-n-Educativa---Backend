"""Modelos SQLAlchemy de catálogos, cédulas y emisiones POA."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.db.base import Base


class PoaObjectiveCatalogModel(Base):
    __tablename__ = "poa_catalogo_objetivos"

    numero: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    clave: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    denominacion: Mapped[str] = mapped_column(Text, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class PoaStrategyCatalogModel(Base):
    __tablename__ = "poa_catalogo_estrategias"

    clave: Mapped[str] = mapped_column(String(20), primary_key=True)
    objetivo_numero: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    denominacion: Mapped[str] = mapped_column(Text, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class PoaIndicatorCatalogModel(Base):
    __tablename__ = "poa_catalogo_indicadores"

    clave: Mapped[str] = mapped_column(String(30), primary_key=True)
    objetivo_numero: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    formula: Mapped[str] = mapped_column(Text, nullable=False)
    unidad_medida: Mapped[str] = mapped_column(String(100), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class PoaActivityCatalogModel(Base):
    __tablename__ = "poa_catalogo_actividades"

    clave: Mapped[str] = mapped_column(String(30), primary_key=True)
    estrategia_clave: Mapped[str] = mapped_column(String(20), nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class PoaFormModel(Base):
    __tablename__ = "poa_cedulas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ejercicio_id: Mapped[int] = mapped_column(Integer, nullable=False)
    objetivo_numero: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    estrategia_clave: Mapped[str] = mapped_column(String(20), nullable=False)
    area_responsable_id: Mapped[int] = mapped_column(Integer, nullable=False)
    alcance_efecto_socioeconomico: Mapped[str | None] = mapped_column(Text)
    tipo_estrategia: Mapped[str | None] = mapped_column(String(40))
    firmantes: Mapped[list[dict[str, str]]] = mapped_column(JSON, nullable=False, default=list)
    creado_por: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PoaFormQuarterModel(Base):
    __tablename__ = "poa_cedula_cuatrimestres"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cedula_id: Mapped[int] = mapped_column(Integer, nullable=False)
    cuatrimestre: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    periodo_id: Mapped[int] = mapped_column(Integer, nullable=False)
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column(Date, nullable=False)


class PoaFormIndicatorModel(Base):
    __tablename__ = "poa_cedula_indicadores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cedula_id: Mapped[int] = mapped_column(Integer, nullable=False)
    indicador_clave: Mapped[str] = mapped_column(String(30), nullable=False)
    meta_institucional: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    linea_base_anio: Mapped[int | None] = mapped_column(SmallInteger)
    linea_base_valor: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    porcentaje_actual: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    meta_numero: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    meta_porcentaje: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    total_alcanzado: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    porcentaje_alcanzado: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PoaFormActivityModel(Base):
    __tablename__ = "poa_cedula_actividades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cedula_id: Mapped[int] = mapped_column(Integer, nullable=False)
    actividad_clave: Mapped[str] = mapped_column(String(30), nullable=False)
    unidad_medida: Mapped[str] = mapped_column(String(100), nullable=False)
    meta_anual: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    area_ejecutora_id: Mapped[int | None] = mapped_column(Integer)
    observaciones: Mapped[str | None] = mapped_column(Text)
    #: Explicacion concreta de la actividad para el area ejecutora ("actividad
    #: UPE Chiapas"): el texto oficial del POA federal es generico.
    actividad_upe: Mapped[str | None] = mapped_column(Text)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PoaFormActivityCriteriaModel(Base):
    """Criterios SEAES que clasifican una actividad: relacion muchos a muchos.

    Reemplaza la columna singular `criterio_seaes_id` (migracion 0028): SEAES
    define siete criterios indicativos y una actividad puede caer en varios.
    """

    __tablename__ = "poa_cedula_actividad_criterios"

    cedula_actividad_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    criterio_seaes_id: Mapped[int] = mapped_column(Integer, primary_key=True)


class PoaActivityFollowUpModel(Base):
    __tablename__ = "poa_cedula_seguimientos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cedula_actividad_id: Mapped[int] = mapped_column(Integer, nullable=False)
    cuatrimestre: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    periodo_id: Mapped[int] = mapped_column(Integer, nullable=False)
    capturado_por: Mapped[int] = mapped_column(Integer, nullable=False)
    programado: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    alcanzado: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    justificacion_desviacion: Mapped[str | None] = mapped_column(Text)
    progreso: Mapped[str | None] = mapped_column(Text)
    alcance: Mapped[str | None] = mapped_column(Text)
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
        default="borrador",
    )
    comentario_revision: Mapped[str | None] = mapped_column(Text)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PoaFormIssueModel(Base):
    __tablename__ = "poa_cedula_emisiones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cedula_id: Mapped[int] = mapped_column(Integer, nullable=False)
    cuatrimestre: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    periodo_id: Mapped[int] = mapped_column(Integer, nullable=False)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    emitido_por: Mapped[int] = mapped_column(Integer, nullable=False)
    emitido_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
