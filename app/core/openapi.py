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
    schema["security"] = [{"bearerAuth": []}]
    app.openapi_schema = schema
    return schema
