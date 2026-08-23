"""Personalizacion de OpenAPI para documentar autenticacion y modulos del backlog."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi


def custom_openapi(app: FastAPI):
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    security_schemes = schema.setdefault("components", {}).setdefault("securitySchemes", {})
    security_schemes["bearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
    }
    security_schemes["refreshCookie"] = {
        "type": "apiKey",
        "in": "cookie",
        "name": app.state.settings.refresh_cookie_name,
        "description": "Cookie HttpOnly rotatoria; JavaScript no puede leer su valor.",
    }
    schema["security"] = [{"bearerAuth": []}]
    prefix = app.state.settings.api_v1_prefix.rstrip("/")
    public_operations = (
        "/health",
        "/health/live",
        "/health/ready",
        f"{prefix}/auth/login",
        f"{prefix}/auth/password-setup",
        f"{prefix}/auth/password-setup/validar",
    )
    for path in public_operations:
        for operation in schema.get("paths", {}).get(path, {}).values():
            if isinstance(operation, dict):
                operation["security"] = []
    refresh_operation = schema.get("paths", {}).get(f"{prefix}/auth/refresh", {}).get("post")
    if refresh_operation:
        refresh_operation["security"] = [{"refreshCookie": []}]
    logout_operation = schema.get("paths", {}).get(f"{prefix}/auth/logout", {}).get("post")
    if logout_operation:
        # La cookie ayuda a revocar la familia, pero es opcional para que el
        # cierre repetido siga siendo idempotente.
        logout_operation["security"] = [{"bearerAuth": []}]

    error_schema = {"$ref": "#/components/schemas/ErrorResponse"}
    error_example = {
        "code": "REQUEST_VALIDATION_ERROR",
        "message": "La solicitud contiene datos invalidos.",
        "details": None,
        "request_id": "req_01JEXAMPLE",
    }
    for path_item in schema.get("paths", {}).values():
        for operation in path_item.values():
            if not isinstance(operation, dict) or "responses" not in operation:
                continue
            responses = operation["responses"]
            if "422" in responses:
                responses["422"] = {
                    "description": "Solicitud o regla de negocio invalida.",
                    "content": {
                        "application/json": {
                            "schema": error_schema,
                            "example": error_example,
                        }
                    },
                }
            responses.setdefault(
                "500",
                {
                    "description": "Error interno seguro.",
                    "content": {
                        "application/json": {
                            "schema": error_schema,
                            "example": {
                                **error_example,
                                "code": "INTERNAL_SERVER_ERROR",
                                "message": "Ocurrio un error interno al procesar la solicitud.",
                            },
                        }
                    },
                },
            )
    for path, path_item in schema.get("paths", {}).items():
        if not path.startswith(f"{prefix}/reportes/"):
            continue
        operation = path_item.get("get")
        if not operation:
            continue
        content = operation.setdefault("responses", {}).setdefault("200", {}).setdefault(
            "content", {}
        )
        content.setdefault(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            {"schema": {"type": "string", "format": "binary"}},
        )
        content.setdefault(
            "application/pdf",
            {"schema": {"type": "string", "format": "binary"}},
        )
    app.openapi_schema = schema
    return schema
