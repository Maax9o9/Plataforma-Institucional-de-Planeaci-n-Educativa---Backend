"""Comando de alta del ejercicio anual."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CreateExerciseCommand:
    year: int
    actor_id: int
