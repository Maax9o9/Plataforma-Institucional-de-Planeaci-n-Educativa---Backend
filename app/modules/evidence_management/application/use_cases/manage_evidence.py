"""Adjuntar y versionar evidencias."""

from __future__ import annotations

from datetime import UTC, datetime

from app.shared.application.event_bus import EventBus
from app.shared.domain.exceptions import ResourceNotFoundError, ValidationError

from ...domain.entities import Evidence, EvidenceLink, EvidenceVersion
from ...domain.events import EvidenceAttached, EvidenceReplaced
from ...domain.ports.repositories import EvidenceRepository
from ..dto import AttachEvidenceCommand, ReplaceEvidenceCommand


class AttachEvidence:
    def __init__(
        self, repository: EvidenceRepository, event_bus: EventBus, access, unit_of_work
    ) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.access = access
        self.unit_of_work = unit_of_work

    async def execute(self, command: AttachEvidenceCommand) -> Evidence:
        async with self.unit_of_work():
            return await self._execute(command)

    async def _execute(self, command: AttachEvidenceCommand) -> Evidence:
        await self.access.ensure_target_editable(command.entity, command.entity_id, command.actor)
        if not command.path_or_url.strip():
            raise ValidationError("La ruta o URL de la evidencia es obligatoria.")
        evidence = Evidence.create(
            name=command.name,
            description=command.description,
            evidence_date=command.evidence_date,
            evidence_type=command.evidence_type,
            uploaded_by=command.actor.id,
        )
        await self.repository.add(evidence)
        await self.repository.add_version(
            EvidenceVersion(
                evidence_id=evidence.id,
                path_or_url=command.path_or_url,
                mime_type=command.mime_type,
                size_bytes=command.size_bytes,
                checksum_sha256=command.checksum_sha256,
                user_id=command.actor.id,
                created_at=datetime.now(UTC),
            )
        )
        await self.repository.link(
            EvidenceLink(
                evidence_id=evidence.id,
                entity=command.entity,
                entity_id=command.entity_id,
                linked_by=command.actor.id,
            )
        )
        await self.event_bus.publish(
            EvidenceAttached(
                actor_id=command.actor.id,
                aggregate_type="evidence",
                aggregate_id=evidence.id,
                action="attached",
                data={"entity": command.entity.value, "entity_id": command.entity_id},
            )
        )
        return evidence


class ReplaceEvidence:
    def __init__(
        self, repository: EvidenceRepository, event_bus: EventBus, access, unit_of_work
    ) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.access = access
        self.unit_of_work = unit_of_work

    async def execute(self, command: ReplaceEvidenceCommand) -> None:
        async with self.unit_of_work():
            await self._execute(command)

    async def _execute(self, command: ReplaceEvidenceCommand) -> None:
        await self.access.ensure_can_replace(command.evidence_id, command.actor)
        if not command.path_or_url.strip():
            raise ValidationError("La ruta o URL de la nueva version es obligatoria.")
        if await self.repository.get(command.evidence_id) is None:
            raise ResourceNotFoundError("La evidencia no existe.")
        await self.repository.add_version(
            EvidenceVersion(
                evidence_id=command.evidence_id,
                path_or_url=command.path_or_url,
                mime_type=command.mime_type,
                size_bytes=command.size_bytes,
                checksum_sha256=command.checksum_sha256,
                user_id=command.actor.id,
                created_at=datetime.now(UTC),
            )
        )
        await self.event_bus.publish(
            EvidenceReplaced(
                actor_id=command.actor.id,
                aggregate_type="evidence",
                aggregate_id=command.evidence_id,
                action="version_added",
                data={"path_or_url": command.path_or_url},
            )
        )
