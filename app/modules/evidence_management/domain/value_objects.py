"""Tipos de evidencia y flujos que pueden vincularla."""

from enum import StrEnum


class EvidenceType(StrEnum):
    FILE = "archivo"
    LINK = "enlace"


class FlowEntity(StrEnum):
    CAPTURE = "captura"
    POA_ADVANCE = "poa_avance"
