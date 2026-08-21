"""Repositorio temporal de evidencias."""

from __future__ import annotations

from itertools import count

from app.shared.domain.exceptions import ConflictError

from ..domain.entities import Evidence, EvidenceLink, EvidenceVersion
from ..domain.value_objects import FlowEntity


class InMemoryEvidenceRepository:
    def __init__(self) -> None:
        self._evidences: dict[int, Evidence] = {}
        self._versions: list[EvidenceVersion] = []
        self._links: set[tuple[int, FlowEntity, int]] = set()
        self._next_id = count(1)

    async def add(self, evidence: Evidence) -> None:
        if evidence.id == 0:
            evidence.id = next(self._next_id)
        self._evidences[evidence.id] = evidence

    async def add_version(self, version: EvidenceVersion) -> None:
        self._versions.append(version)

    async def link(self, link: EvidenceLink) -> None:
        key = (link.evidence_id, link.entity, link.entity_id)
        if key in self._links:
            raise ConflictError("La evidencia ya esta vinculada a ese registro.")
        self._links.add(key)

    async def has_for(self, entity: FlowEntity, entity_id: int) -> bool:
        return any(
            item_entity == entity and item_id == entity_id
            for _, item_entity, item_id in self._links
        )

    async def get(self, evidence_id: int) -> Evidence | None:
        return self._evidences.get(evidence_id)

    async def list_all(self) -> list[Evidence]:
        return list(self._evidences.values())

    async def list_for(self, entity: FlowEntity, entity_id: int) -> list[Evidence]:
        evidence_ids = {
            evidence_id
            for evidence_id, item_entity, item_id in self._links
            if item_entity == entity and item_id == entity_id
        }
        return [self._evidences[item_id] for item_id in sorted(evidence_ids)]

    async def list_versions(self, evidence_id: int) -> list[EvidenceVersion]:
        return sorted(
            [item for item in self._versions if item.evidence_id == evidence_id],
            key=lambda item: item.created_at,
        )

    async def unlink(self, evidence_id: int, entity: FlowEntity, entity_id: int) -> bool:
        key = (evidence_id, entity, entity_id)
        if key not in self._links:
            return False
        self._links.remove(key)
        return True
