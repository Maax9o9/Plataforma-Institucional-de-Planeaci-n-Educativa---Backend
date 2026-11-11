"""Reutilizar una evidencia existente sin duplicar versiones."""

from app.shared.application.event_bus import EventBus
from app.shared.domain.exceptions import ResourceNotFoundError

from ...domain.entities import EvidenceLink
from ...domain.events import EvidenceLinked, EvidenceUnlinked
from ...domain.ports.repositories import EvidenceRepository
from ..dto import LinkExistingEvidenceCommand, UnlinkEvidenceCommand


class LinkExistingEvidence:
    def __init__(
        self, repository: EvidenceRepository, event_bus: EventBus, access, unit_of_work
    ) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.access = access
        self.unit_of_work = unit_of_work

    async def execute(self, command: LinkExistingEvidenceCommand):
        async with self.unit_of_work():
            await self._execute(command)

    async def _execute(self, command: LinkExistingEvidenceCommand):
        await self.access.ensure_target_editable(command.entity, command.entity_id, command.actor)
        await self.access.ensure_can_view(command.evidence_id, command.actor)
        if await self.repository.get(command.evidence_id) is None:
            raise ResourceNotFoundError("La evidencia no existe.")
        await self.repository.link(
            EvidenceLink(
                evidence_id=command.evidence_id,
                entity=command.entity,
                entity_id=command.entity_id,
                linked_by=command.actor.id,
            )
        )
        await self.event_bus.publish(
            EvidenceLinked(
                actor_id=command.actor.id,
                aggregate_type="evidence",
                aggregate_id=command.evidence_id,
                action="linked",
                data={"entity": command.entity.value, "entity_id": command.entity_id},
            )
        )


class UnlinkEvidence:
    def __init__(
        self, repository: EvidenceRepository, event_bus: EventBus, access, unit_of_work
    ) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.access = access
        self.unit_of_work = unit_of_work

    async def execute(self, command: UnlinkEvidenceCommand) -> None:
        async with self.unit_of_work():
            await self.access.ensure_target_editable(
                command.entity, command.entity_id, command.actor
            )
            removed = await self.repository.unlink(
                command.evidence_id, command.entity, command.entity_id
            )
            if not removed:
                raise ResourceNotFoundError("La evidencia no esta vinculada al registro.")
            await self.event_bus.publish(
                EvidenceUnlinked(
                    actor_id=command.actor.id,
                    aggregate_type="evidence",
                    aggregate_id=command.evidence_id,
                    action="unlinked",
                    data={"entity": command.entity.value, "entity_id": command.entity_id},
                )
            )
