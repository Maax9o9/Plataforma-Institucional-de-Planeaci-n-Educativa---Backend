"""Texto editable; el diseño y los datos de seguridad no se editan desde HTTP."""

import re
from dataclasses import dataclass
from datetime import datetime

from app.shared.domain.exceptions import ValidationError

LIMITS = {"asunto": 180, "titulo": 160, "cuerpo": 6000, "texto_boton": 60}


def validate_content(content: dict[str, str]) -> dict[str, str]:
    clean = {}
    for field, value in content.items():
        if field not in LIMITS:
            raise ValidationError("El campo de correo no es editable.", details={"field": field})
        if not isinstance(value, str) or not value.strip() or len(value) > LIMITS[field]:
            raise ValidationError(
                "El texto está vacío o excede la longitud permitida.",
                details={"field": field, "max_length": LIMITS[field]},
            )
        if any(ord(char) < 32 and char not in "\n\t" for char in value):
            raise ValidationError(
                "El texto contiene caracteres de control.", details={"field": field}
            )
        if field != "cuerpo" and "\n" in value:
            raise ValidationError("Este campo debe tener una sola línea.", details={"field": field})
        rest = value.replace("{{nombre}}", "")
        if "{{" in rest or "}}" in rest:
            raise ValidationError(
                "La única variable de texto admitida es {{nombre}}.", details={"field": field}
            )
        clean[field] = value.strip()
    return clean


def personalize(value: str, name: str) -> str:
    # No evaluar expresiones, atributos ni plantillas suministradas por el usuario.
    name = re.sub(r"[\x00-\x1f\x7f]", " ", name).strip()[:150]
    return value.replace("{{nombre}}", name or "usuario/a")


@dataclass(frozen=True)
class TemplateDefinition:
    key: str
    label: str
    content: dict[str, str]


@dataclass(frozen=True)
class TemplateOverride:
    key: str
    content: dict[str, str]
    version: int
    updated_by: int
    updated_at: datetime
