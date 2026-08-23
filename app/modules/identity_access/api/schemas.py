"""DTOs HTTP separados de las entidades de dominio."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator

from ..domain.entities import User
from ..domain.value_objects import Role


class LoginRequest(BaseModel):
    correo: EmailStr = Field(
        description="Correo institucional.",
        examples=["admin@upchiapas.edu.mx"],
    )
    contrasena: str = Field(
        min_length=1,
        description="Contrasena del usuario.",
        examples=["Admin12345!"],
    )


class LoginResponse(BaseModel):
    access_token: str = Field(description="JWT de corta duracion para llamadas autenticadas.")
    token_type: Literal["bearer"] = Field(description="Esquema de autenticacion.")
    expires_in: int = Field(description="Segundos de vigencia del access token.", examples=[900])


class UsuarioCreateRequest(BaseModel):
    correo: EmailStr = Field(
        description="Correo institucional unico.",
        examples=["responsable@upchiapas.edu.mx"],
    )
    nombre: str = Field(
        min_length=2,
        max_length=150,
        description="Nombre completo del usuario.",
        examples=["Responsable de Planeacion"],
    )
    contrasena: str | None = Field(
        default=None,
        min_length=8,
        description="Contrasena que se almacenara usando Argon2.",
        examples=["Una-clave-local-segura"],
    )
    roles: set[Role] = Field(
        default_factory=lambda: {Role.CONSULTA},
        description="Roles RBAC asignados al usuario.",
        examples=[["consulta"]],
    )
    area_id: int | None = Field(
        default=None,
        description="Area institucional del usuario cuando corresponda.",
    )


class ActualizarUsuarioRequest(BaseModel):
    correo: EmailStr | None = None
    nombre: str | None = Field(default=None, min_length=2, max_length=150)
    roles: set[Role] | None = None
    area_id: int | None = None
    notificar_correo: bool | None = None
    version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def require_one_change(self) -> ActualizarUsuarioRequest:
        if all(
            value is None
            for value in (
                self.correo,
                self.nombre,
                self.roles,
                self.area_id,
                self.notificar_correo,
            )
        ):
            raise ValueError("Debe indicar al menos un campo para actualizar.")
        return self


class UsuarioResponse(BaseModel):
    id: int
    correo: EmailStr
    nombre: str
    roles: list[Role]
    area_id: int | None
    area_nombre: str | None
    activo: bool
    notificar_correo: bool
    requiere_configurar_contrasena: bool
    ultimo_acceso: datetime | None
    creado_en: datetime
    actualizado_en: datetime
    version: int

    @classmethod
    def from_domain(cls, user: User) -> UsuarioResponse:
        return cls(
            id=user.id,
            correo=user.email.value,
            nombre=user.full_name,
            roles=sorted(user.roles, key=lambda role: role.value),
            area_id=user.area_id,
            area_nombre=user.area_name,
            activo=user.is_active,
            notificar_correo=user.notify_email,
            requiere_configurar_contrasena=user.password_setup_required,
            ultimo_acceso=user.last_access_at,
            creado_en=user.created_at,
            actualizado_en=user.updated_at,
            version=user.version,
        )


class PaginaUsuariosResponse(BaseModel):
    items: list[UsuarioResponse]
    total: int
    offset: int
    limit: int


class ConfigurarContrasenaRequest(BaseModel):
    token: str = Field(min_length=1)
    contrasena: str = Field(min_length=8)


class ValidarEnlaceContrasenaRequest(BaseModel):
    token: str = Field(min_length=1)
