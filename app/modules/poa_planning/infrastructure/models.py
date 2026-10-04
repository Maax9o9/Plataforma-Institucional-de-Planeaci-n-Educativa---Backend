"""Modelo del ejercicio anual utilizado por las cédulas."""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, Integer, SmallInteger, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.db.base import Base


class PoaExerciseModel(Base):
    __tablename__ = "poa_ejercicios"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    anio: Mapped[int] = mapped_column(SmallInteger, nullable=False, unique=True)
    estado: Mapped[str] = mapped_column(
        Enum(
            "borrador",
            "enviado",
            "vigente",
            "cerrado",
            name="estado_ejercicio_poa",
            native_enum=True,
            create_type=False,
        ),
        nullable=False,
        default="borrador",
    )
    fecha_limite_formulacion: Mapped[date | None] = mapped_column(Date)
    comentario_revision: Mapped[str | None] = mapped_column(Text)
    cerrado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
