"""Modelo del ejercicio anual utilizado por las cédulas."""

from sqlalchemy import Integer, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.db.base import Base


class PoaExerciseModel(Base):
    __tablename__ = "poa_ejercicios"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    anio: Mapped[int] = mapped_column(SmallInteger, nullable=False, unique=True)
