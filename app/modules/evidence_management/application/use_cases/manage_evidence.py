"""Adjuntar y versionar evidencias."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from urllib.parse import urlsplit

from app.shared.application.event_bus import EventBus
from app.shared.domain.exceptions import ResourceNotFoundError, ValidationError

from ...domain.entities import Evidence, EvidenceLink, EvidenceVersion
from ...domain.events import EvidenceAttached, EvidenceReplaced
from ...domain.ports.repositories import EvidenceRepository
from ..dto import AttachEvidenceCommand, ReplaceEvidenceCommand

SAFE_STORED_FILE = re.compile(r"^[0-9a-f]{32}\.(?:pdf|png|jpg)$")


def _validate_reference(
    evidence_type,
    path_or_url: str,
    mime_type: str | None,
    size_bytes: int | None,
    checksum_sha256: str | None,
) -> None:
    value = path_or_url.strip()
    if evidence_type.value == "enlace":
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ValidationError("Los enlaces de evidencia deben usar una URL https valida.")
        return
    if not SAFE_STORED_FILE.fullmatch(value):
        raise ValidationError("El archivo debe provenir del endpoint seguro de carga.")
    if not mime_type or size_bytes is None or not checksum_sha256:
        raise ValidationError("MIME, tamano y checksum son obligatorios para archivos.")


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
        _validate_reference(
            command.evidence_type,
            command.path_or_url,
            command.mime_type,
            command.size_bytes,
            command.checksum_sha256,
        )
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
        evidence = await self.repository.get(command.evidence_id)
        if evidence is None:
            raise ResourceNotFoundError("La evidencia no existe.")
        _validate_reference(
            evidence.evidence_type,
            command.path_or_url,
            command.mime_type,
            command.size_bytes,
            command.checksum_sha256,
        )
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
