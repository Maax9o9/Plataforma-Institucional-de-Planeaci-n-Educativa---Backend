"""Schemas HTTP transversales."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    code: str = Field(description="Codigo estable para el consumidor de la API.")
    message: str = Field(description="Descripcion legible del error.")
    details: Any | None = Field(default=None, description="Detalles adicionales de validacion.")
    request_id: str | None = Field(
        default=None,
        description="Identificador de la solicitud para correlacionar respuesta y logs.",
    )
