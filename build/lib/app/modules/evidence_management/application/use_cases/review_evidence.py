"""Dictamen de Planeación sobre una evidencia."""

from __future__ import annotations

from datetime import UTC, datetime

from app.shared.application.event_bus import EventBus
from app.shared.domain.exceptions import ForbiddenError, ResourceNotFoundError, ValidationError

from ...domain.entities import Evidence
from ...domain.ports.repositories import EvidenceRepository
from ..dto import ReviewEvidenceCommand

#: Quién dictamina una evidencia: los mismos que dictaminan el informe que la
#: contiene. Si fueran distintos, una evidencia podría quedar aprobada por
#: alguien que no puede validar el informe del que forma parte.
REVIEW_ROLES = ("planeacion", "planeacion_admin", "admin_sistema", "revisor_poa")


class ReviewEvidence:
    def __init__(self, repository: EvidenceRepository, event_bus: EventBus) -> None:
        self.repository = repository
        self.event_bus = event_bus

    async def execute(self, command: ReviewEvidenceCommand) -> Evidence:
        if not command.actor.has_any_role(*REVIEW_ROLES):
            raise ForbiddenError(
                "Dictaminar evidencias es de Planeación.",
                details={"reason": "EVIDENCE_REVIEW_FORBIDDEN"},
            )

        evidence = await self.repository.get(command.evidence_id)
        if evidence is None:
            raise ResourceNotFoundError("La evidencia no existe.")

        ahora = datetime.now(UTC)
        if command.approved:
            evidence.approve(reviewer_id=command.actor.id, at=ahora)
        else:
            if command.comment is None:
                raise ValidationError("Indique por qué la evidencia no sirve.")
            evidence.reject(reviewer_id=command.actor.id, at=ahora, comment=command.comment)

        await self.repository.save_review(evidence)
        return evidence
