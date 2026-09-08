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
