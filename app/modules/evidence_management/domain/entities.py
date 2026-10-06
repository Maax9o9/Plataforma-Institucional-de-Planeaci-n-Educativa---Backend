"""Entidades de evidencias versionables y reutilizables."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from app.shared.domain.base_entity import BaseEntity
from app.shared.domain.exceptions import ValidationError

from .value_objects import EvidenceType, FlowEntity


def normalizar_criterios(ids: tuple[int, ...] | list[int]) -> tuple[int, ...]:
    """Sin repetidos y en orden estable.

    El orden no lo decide quien manda la lista: dos evidencias con los mismos
    criterios tienen que verse iguales, y repetir uno no significa nada.
    """
    return tuple(sorted(set(ids)))


@dataclass(kw_only=True)
class Evidence(BaseEntity):
    name: str
    description: str
    evidence_date: date
    evidence_type: EvidenceType
    uploaded_by: int
    #: A qué criterios del SEAES responde esta evidencia. Opcional e
    #: indicativo: un documento puede servir para varios criterios, o para
    #: ninguno. Obligarlo lo volvería un trámite que se rellena con lo primero
    #: que aparezca, y la cobertura SEAES dejaría de significar algo.
    criteria_seaes_ids: tuple[int, ...] = ()

    @classmethod
    def create(
        cls,
        *,
        name: str,
        description: str,
        evidence_date: date,
        evidence_type: EvidenceType,
        uploaded_by: int,
        criteria_seaes_ids: tuple[int, ...] = (),
    ) -> Evidence:
        if not name.strip() or not description.strip():
            raise ValidationError("Nombre y descripcion son obligatorios para la evidencia.")
        return cls(
            name=name.strip(),
            description=description.strip(),
            evidence_date=evidence_date,
            evidence_type=evidence_type,
            uploaded_by=uploaded_by,
            criteria_seaes_ids=normalizar_criterios(criteria_seaes_ids),
        )


@dataclass(frozen=True)
class EvidenceVersion:
    evidence_id: int
    path_or_url: str
    mime_type: str | None
    size_bytes: int | None
    checksum_sha256: str | None
    user_id: int
    created_at: datetime


@dataclass(frozen=True)
class EvidenceLink:
    evidence_id: int
    entity: FlowEntity
    entity_id: int
    linked_by: int
