"""Modelos SQLAlchemy propiedad de identity_access.

Las tablas se crean exclusivamente mediante ``bd/migrations``. Estos modelos
solo describen las tablas existentes para que los repositorios puedan leerlas.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.db.base import Base


class UserModel(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    correo: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    hash_password: Mapped[str] = mapped_column(String(255), nullable=False)
    area_id: Mapped[int | None] = mapped_column(Integer)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notificar_correo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    requiere_configurar_contrasena: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UserRoleModel(Base):
    __tablename__ = "usuario_roles"

    usuario_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rol: Mapped[str] = mapped_column(
        Enum(
            "planeacion",
            "responsable_area",
            "rectoria",
            "consulta",
            "admin_sistema",
            name="rol",
            native_enum=True,
            create_type=False,
        ),
        primary_key=True,
    )


class RefreshTokenModel(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(Integer, nullable=False)
    jti: Mapped[UUID] = mapped_column(unique=True, nullable=False)
    hash_token: Mapped[str] = mapped_column(String(255), nullable=False)
    session_id: Mapped[UUID | None] = mapped_column(nullable=True)
    emitido_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revocado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AccessLogModel(Base):
    __tablename__ = "bitacora_accesos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(Integer)
    correo_intentado: Mapped[str] = mapped_column(String(200), nullable=False)
    exitoso: Mapped[bool] = mapped_column(Boolean, nullable=False)
    motivo_fallo: Mapped[str | None] = mapped_column(String(100))
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PasswordSetupTokenModel(Base):
    __tablename__ = "tokens_configuracion_contrasena"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(Integer, nullable=False)
    hash_token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    usado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
