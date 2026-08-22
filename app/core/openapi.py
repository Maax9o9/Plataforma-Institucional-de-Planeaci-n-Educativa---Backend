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
        logout_operation["security"] = [{"bearerAuth": [], "refreshCookie": []}]
    app.openapi_schema = schema
    return schema
