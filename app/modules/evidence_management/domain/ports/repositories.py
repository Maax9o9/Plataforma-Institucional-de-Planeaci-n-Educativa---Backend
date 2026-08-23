"""Puertos de evidencia consumibles por indicadores y POA."""

from __future__ import annotations

from typing import Protocol

from ..entities import Evidence, EvidenceLink, EvidenceVersion
from ..value_objects import FlowEntity


class EvidenceRepository(Protocol):
    async def add(self, evidence: Evidence) -> None: ...

    async def add_version(self, version: EvidenceVersion) -> None: ...

    async def link(self, link: EvidenceLink) -> None: ...

    async def has_for(self, entity: FlowEntity, entity_id: int) -> bool: ...

    async def get(self, evidence_id: int) -> Evidence | None: ...

    async def list_all(self) -> list[Evidence]: ...

    async def list_for(self, entity: FlowEntity, entity_id: int) -> list[Evidence]: ...

    async def list_versions(self, evidence_id: int) -> list[EvidenceVersion]: ...

    async def list_versions_page(
        self,
        evidence_id: int,
        *,
        offset: int,
        limit: int,
        descending: bool,
    ) -> tuple[list[tuple[int, EvidenceVersion]], int]: ...

    async def list_links(self, evidence_id: int) -> list[EvidenceLink]: ...

    async def find_evidence_id_by_path(self, path: str) -> int | None: ...

    async def unlink(self, evidence_id: int, entity: FlowEntity, entity_id: int) -> bool: ...
