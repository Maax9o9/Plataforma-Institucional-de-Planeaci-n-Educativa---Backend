"""Objetos de valor pequenos y reutilizables."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .exceptions import ValidationError

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True)
class Email:
    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().lower()
        if not _EMAIL_PATTERN.fullmatch(normalized):
            raise ValidationError("El correo electronico no tiene un formato valido.")
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value
