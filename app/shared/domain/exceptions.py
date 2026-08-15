"""Excepciones de negocio que pueden traducirse a respuestas HTTP."""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Error controlado que conserva un codigo estable para los consumidores."""

    code = "APP_ERROR"
    status_code = 400
    default_message = "La operacion no pudo completarse."

    def __init__(self, message: str | None = None, details: Any = None) -> None:
        self.message = message or self.default_message
        self.details = details
        super().__init__(self.message)


class AuthenticationError(AppError):
    code = "AUTHENTICATION_REQUIRED"
    status_code = 401
    default_message = "Las credenciales o el token no son validos."


class ForbiddenError(AppError):
    code = "FORBIDDEN"
    status_code = 403
    default_message = "El usuario no tiene permisos para esta operacion."


class ResourceNotFoundError(AppError):
    code = "RESOURCE_NOT_FOUND"
    status_code = 404
    default_message = "El recurso solicitado no existe."


class ConflictError(AppError):
    code = "CONFLICT"
    status_code = 409
    default_message = "La operacion entra en conflicto con el estado actual."


class InvalidStateError(AppError):
    code = "INVALID_STATE"
    status_code = 422
    default_message = "El recurso no permite esta transicion de estado."


class ValidationError(AppError):
    code = "BUSINESS_VALIDATION_ERROR"
    status_code = 422
    default_message = "Los datos no cumplen las reglas de negocio."
