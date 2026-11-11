"""Modelo SQLAlchemy de cambios_estado, propiedad lógica de validation."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.db.base import Base


class StateChangeModel(Base):
    __tablename__ = "cambios_estado"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entidad: Mapped[str] = mapped_column(
        Enum(
            "captura",
            "poa_avance",
            "poa_cedula_seguimiento",
            "poa_ejercicio",
            name="entidad_flujo",
            native_enum=True,
            create_type=False,
        ),
        nullable=False,
    )
    entidad_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # 'vigente' y 'cerrado' son del ciclo del ejercicio POA (migracion 0030):
    # el ejercicio no reutiliza este enum para su propio estado, pero el
    # historial compartido en cambios_estado si necesita esos valores.
    de_estado: Mapped[str | None] = mapped_column(
        Enum(
            "borrador",
            "enviado",
            "validado",
            "rechazado",
            "vigente",
            "cerrado",
            name="estado_captura",
            native_enum=True,
            create_type=False,
        )
    )
    a_estado: Mapped[str] = mapped_column(
        Enum(
            "borrador",
            "enviado",
            "validado",
            "rechazado",
            "vigente",
            "cerrado",
            name="estado_captura",
            native_enum=True,
            create_type=False,
        ),
        nullable=False,
    )
    usuario_id: Mapped[int] = mapped_column(Integer, nullable=False)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    comentario: Mapped[str | None] = mapped_column(Text)
