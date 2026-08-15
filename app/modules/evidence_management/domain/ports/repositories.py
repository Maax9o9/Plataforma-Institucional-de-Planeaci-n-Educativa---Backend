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
