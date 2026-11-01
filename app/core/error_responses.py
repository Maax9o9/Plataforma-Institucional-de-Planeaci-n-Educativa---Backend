"""Lo que una operacion declara que puede devolver cuando falla."""

from __future__ import annotations

from typing import Any

from app.core.schemas import ErrorResponse
from app.shared.domain.exceptions import AppError

CONTRATO_DEL_ERROR = {"$ref": "#/components/schemas/ErrorResponse"}

SOLICITUD_DE_EJEMPLO = "req_01JEXAMPLE"

ERRORES_QUE_CUALQUIER_OPERACION_PUEDE_DEVOLVER = (
    ("503", "SERVICE_UNAVAILABLE", "Servicio de datos temporalmente no disponible."),
    ("409", "CONFLICT", "Conflicto con un registro o versión existente."),
)


def ejemplo_del_error(code: str, message: str) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "details": None,
        "request_id": SOLICITUD_DE_EJEMPLO,
    }


def respuesta_de_error(code: str, message: str) -> dict[str, Any]:
    return {
        "description": message,
        "content": {
            "application/json": {
                "schema": CONTRATO_DEL_ERROR,
                "example": ejemplo_del_error(code, message),
            }
        },
    }


def los_errores_que_devuelve(*errores: type[AppError]) -> dict[int | str, dict[str, Any]]:
    por_estado: dict[int, list[type[AppError]]] = {}
    for error in errores:
        por_estado.setdefault(error.status_code, []).append(error)
    return {
        estado: {
            "model": ErrorResponse,
            "description": " ".join(error.default_message for error in grupo),
            "content": {
                "application/json": {
                    "examples": {
                        error.code: {
                            "summary": error.default_message,
                            "value": ejemplo_del_error(error.code, error.default_message),
                        }
                        for error in grupo
                    }
                }
            },
        }
        for estado, grupo in por_estado.items()
    }
