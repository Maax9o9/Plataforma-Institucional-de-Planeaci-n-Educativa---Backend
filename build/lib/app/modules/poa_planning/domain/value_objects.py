"""Vocabulario del ciclo del ejercicio anual del POA."""

from __future__ import annotations

from enum import StrEnum


class PoaExerciseStatus(StrEnum):
    """Estados del ejercicio anual.

    No reutiliza `CaptureStatus`: un POA aprobado no se queda quieto como una
    captura validada, entra en vigor (`ACTIVE`) y, al terminar el año, se
    cierra (`CLOSED`). El ciclo de revisión (enviar/aprobar/devolver) sí se
    comparte con el seguimiento cuatrimestral, pero el vocabulario de estados
    es propio del ejercicio.
    """

    DRAFT = "borrador"
    SENT = "enviado"
    ACTIVE = "vigente"
    CLOSED = "cerrado"
