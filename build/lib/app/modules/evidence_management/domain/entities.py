"""Entidades de evidencias versionables y reutilizables."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from app.shared.domain.base_entity import BaseEntity
from app.shared.domain.exceptions import ValidationError

from .value_objects import EvidenceReviewStatus, EvidenceType, FlowEntity


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
    review_status: EvidenceReviewStatus = EvidenceReviewStatus.PENDING
    reviewed_by: int | None = None
    reviewed_at: datetime | None = None
    review_comment: str | None = None

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

    def approve(self, *, reviewer_id: int, at: datetime) -> None:
        """La evidencia sostiene lo que el área reportó. Aprobar no necesita
        explicación: lo que hay que explicar es por qué algo no sirve."""
        self.review_status = EvidenceReviewStatus.APPROVED
        self.reviewed_by = reviewer_id
        self.reviewed_at = at
        self.review_comment = None

    def reject(self, *, reviewer_id: int, at: datetime, comment: str) -> None:
        """La evidencia no sostiene lo reportado.

        El motivo es obligatorio: sin él el área queda adivinando qué reponer,
        que es justo lo que esta marca viene a evitar. No bloquea el dictamen
        del informe —eso se decide aparte—, señala qué archivo corregir.
        """
        if not comment.strip():
            raise ValidationError("Indique por qué la evidencia no sirve.")
        self.review_status = EvidenceReviewStatus.REJECTED
        self.reviewed_by = reviewer_id
        self.reviewed_at = at
        self.review_comment = comment.strip()


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
