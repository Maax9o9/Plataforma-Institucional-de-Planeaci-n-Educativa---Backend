"""Objetos de valor propios de identidad."""

from __future__ import annotations

from enum import StrEnum

from app.shared.domain.exceptions import ValidationError


class Role(StrEnum):
    PLANEACION = "planeacion"
    PLANEACION_ADMIN = "planeacion_admin"
    CAPTURISTA_POA = "capturista_poa"
    REVISOR_POA = "revisor_poa"
    RESPONSABLE_AREA = "responsable_area"
    RECTORIA = "rectoria"
    CONSULTA = "consulta"
    ADMIN_SISTEMA = "admin_sistema"

    @classmethod
    def from_value(cls, value: str) -> Role:
        try:
            return cls(value)
        except ValueError as exc:
            raise ValidationError(
                "El rol indicado no existe.",
                details={"role": value, "allowed": [role.value for role in cls]},
            ) from exc
