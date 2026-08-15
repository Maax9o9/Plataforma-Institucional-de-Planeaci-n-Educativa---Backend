"""Schemas HTTP de reportes."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ReporteRespuesta(BaseModel):
    tipo: str
    filtros: dict[str, Any]
    filas: list[dict[str, Any]]
    formato: Literal["json"] = "json"


class FormatoReporte(BaseModel):
    formato: Literal["json"] = Field(default="json", description="Formato disponible en esta fase.")
