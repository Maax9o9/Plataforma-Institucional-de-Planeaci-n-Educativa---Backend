"""Estados de una captura de indicador."""

from enum import StrEnum


class CaptureStatus(StrEnum):
    DRAFT = "borrador"
    SENT = "enviado"
    VALIDATED = "validado"
    REJECTED = "rechazado"
