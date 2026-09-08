"""Modelos SQLAlchemy propiedad de evidence_management."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.db.base import Base


class EvidenceModel(Base):
    __tablename__ = "evidencias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(300), nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    tipo: Mapped[str] = mapped_column(
        Enum("archivo", "enlace", name="tipo_evidencia", native_enum=True, create_type=False),
        nullable=False,
    )
    subida_por: Mapped[int] = mapped_column(Integer, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EvidenceLinkModel(Base):
    __tablename__ = "evidencia_vinculos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    evidencia_id: Mapped[int] = mapped_column(Integer, nullable=False)
    entidad: Mapped[str] = mapped_column(
        Enum(
            "captura",
            "poa_avance",
            "poa_cedula_seguimiento",
            name="entidad_flujo",
            native_enum=True,
            create_type=False,
        ),
        nullable=False,
    )
    entidad_id: Mapped[int] = mapped_column(Integer, nullable=False)
    vinculado_por: Mapped[int] = mapped_column(Integer, nullable=False)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EvidenceVersionModel(Base):
    __tablename__ = "evidencia_versiones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    evidencia_id: Mapped[int] = mapped_column(Integer, nullable=False)
    ruta_o_url: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(100))
    tamanio_bytes: Mapped[int | None] = mapped_column()
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    usuario_id: Mapped[int] = mapped_column(Integer, nullable=False)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
