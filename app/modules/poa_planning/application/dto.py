"""Comando de alta del ejercicio anual."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class CreateExerciseCommand:
    year: int
    actor_id: int
    formulation_deadline: date | None = None
