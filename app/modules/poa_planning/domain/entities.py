"""Ejercicio anual compartido por las cédulas POA."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from app.shared.domain.base_entity import BaseEntity, utc_now
from app.shared.domain.exceptions import InvalidStateError, ValidationError

from .value_objects import PoaExerciseStatus


@dataclass(kw_only=True)
class PoaExercise(BaseEntity):
    year: int
    status: PoaExerciseStatus = PoaExerciseStatus.DRAFT
    formulation_deadline: date | None = None
    review_comment: str | None = None
    closed_at: datetime | None = None

    @classmethod
    def create(cls, year: int, *, formulation_deadline: date | None = None) -> PoaExercise:
        if not 2000 <= year <= 2200:
            raise ValidationError("El año del ejercicio POA no es válido.")
        return cls(year=year, formulation_deadline=formulation_deadline)

    def ensure_editable(self, today: date) -> None:
        """Planeación sólo edita la estructura en borrador y antes de la fecha límite."""
        if self.status is not PoaExerciseStatus.DRAFT:
            raise InvalidStateError(
                "El ejercicio ya no está en formulación; no puede editarse."
            )
        if self.formulation_deadline is not None and today > self.formulation_deadline:
            raise InvalidStateError(
                "La fecha límite de formulación ya pasó; el ejercicio no puede editarse."
            )

    def send(self, *, has_forms: bool) -> None:
        """Planeación manda el ejercicio a Rectoría para su aprobación.

        "Devuelto" no es un estado aparte: `reject()` regresa el ejercicio a
        `borrador` conservando el motivo, así que enviar de nuevo sólo exige
        estar en borrador.
        """
        if self.status is not PoaExerciseStatus.DRAFT:
            raise InvalidStateError(
                "Sólo un ejercicio en borrador puede enviarse a Rectoría."
            )
        if not has_forms:
            raise ValidationError(
                "El ejercicio POA necesita al menos una cédula para enviarse a Rectoría."
            )
        self.status = PoaExerciseStatus.SENT
        self.touch()

    def approve(self) -> None:
        """Rectoría aprueba el ejercicio: entra en vigor."""
        if self.status is not PoaExerciseStatus.SENT:
            raise InvalidStateError("Sólo un ejercicio enviado puede aprobarse.")
        self.status = PoaExerciseStatus.ACTIVE
        self.review_comment = None
        self.touch()

    def reject(self, comment: str) -> None:
        """Rectoría devuelve el ejercicio con el motivo visible para Planeación."""
        if self.status is not PoaExerciseStatus.SENT:
            raise InvalidStateError("Sólo un ejercicio enviado puede devolverse.")
        normalized = comment.strip()
        if not normalized:
            raise ValidationError("El comentario es obligatorio al devolver el ejercicio.")
        self.status = PoaExerciseStatus.DRAFT
        self.review_comment = normalized
        self.touch()

    def close(self) -> None:
        """Planeación cierra el ejercicio al terminar el año."""
        if self.status is not PoaExerciseStatus.ACTIVE:
            raise InvalidStateError("Sólo un ejercicio vigente puede cerrarse.")
        self.status = PoaExerciseStatus.CLOSED
        self.closed_at = utc_now()
        self.touch()
