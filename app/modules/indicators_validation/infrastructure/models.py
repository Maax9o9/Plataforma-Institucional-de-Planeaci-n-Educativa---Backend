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
        Enum("captura", "poa_avance", name="entidad_flujo", native_enum=True, create_type=False),
        nullable=False,
    )
    entidad_id: Mapped[int] = mapped_column(Integer, nullable=False)
    de_estado: Mapped[str | None] = mapped_column(
        Enum(
            "borrador",
            "enviado",
            "validado",
            "rechazado",
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
            name="estado_captura",
            native_enum=True,
            create_type=False,
        ),
        nullable=False,
    )
    usuario_id: Mapped[int] = mapped_column(Integer, nullable=False)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    comentario: Mapped[str | None] = mapped_column(Text)
