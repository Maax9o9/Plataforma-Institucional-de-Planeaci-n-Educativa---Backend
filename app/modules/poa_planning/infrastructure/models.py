"""Modelos SQLAlchemy propietarios de poa_planning."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Integer, Numeric, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.db.base import Base


class PoaExerciseModel(Base):
    __tablename__ = "poa_ejercicios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    anio: Mapped[int] = mapped_column(SmallInteger, nullable=False, unique=True)


class PoaProcessModel(Base):
    __tablename__ = "poa_procesos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ejercicio_id: Mapped[int] = mapped_column(Integer, nullable=False)
    nombre: Mapped[str] = mapped_column(String(300), nullable=False)
    area_id: Mapped[int] = mapped_column(Integer, nullable=False)


class PoaObjectiveModel(Base):
    __tablename__ = "poa_objetivos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proceso_id: Mapped[int] = mapped_column(Integer, nullable=False)
    indicador_poa: Mapped[str | None] = mapped_column(String(300))
    objetivo: Mapped[str] = mapped_column(Text, nullable=False)


class PoaActivityModel(Base):
    __tablename__ = "poa_actividades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    objetivo_id: Mapped[int] = mapped_column(Integer, nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    unidad_medida: Mapped[str] = mapped_column(String(100), nullable=False)
    meta_anual: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    observaciones: Mapped[str | None] = mapped_column(Text)
    responsable_id: Mapped[int] = mapped_column(Integer, nullable=False)
