"""Reutilizar una evidencia existente sin duplicar versiones."""

from app.shared.application.event_bus import EventBus
from app.shared.domain.exceptions import ResourceNotFoundError

from ...domain.entities import EvidenceLink
from ...domain.ports.repositories import EvidenceRepository
from ..dto import LinkExistingEvidenceCommand


class LinkExistingEvidence:
    def __init__(self, repository: EvidenceRepository, event_bus: EventBus) -> None:
        self.repository = repository
        self.event_bus = event_bus

    async def execute(self, command: LinkExistingEvidenceCommand):
        if await self.repository.get(command.evidence_id) is None:
            raise ResourceNotFoundError("La evidencia no existe.")
        await self.repository.link(
            EvidenceLink(
                evidence_id=command.evidence_id,
                entity=command.entity,
                entity_id=command.entity_id,
                linked_by=command.actor_id,
            )
        )
