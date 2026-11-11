"""Tipos de evidencia y flujos que pueden vincularla."""

from enum import StrEnum


class EvidenceType(StrEnum):
    FILE = "archivo"
    LINK = "enlace"


class FlowEntity(StrEnum):
    CAPTURE = "captura"
    # Sólo para decodificar vínculos históricos; no admitido por los endpoints actuales.
    POA_ADVANCE = "poa_avance"
    POA_FORM_FOLLOW_UP = "poa_cedula_seguimiento"


class EvidenceReviewStatus(StrEnum):
    """Dictamen de Planeación sobre una evidencia.

    Informa el dictamen del informe cuatrimestral; no lo bloquea. Ese sigue
    siendo uno solo —validar o devolver con motivo—, y un segundo candado sobre
    las piezas dejaría al área trabada sin saber cuál de los dos la detiene.
    """

    PENDING = "pendiente"
    APPROVED = "aprobada"
    REJECTED = "rechazada"
