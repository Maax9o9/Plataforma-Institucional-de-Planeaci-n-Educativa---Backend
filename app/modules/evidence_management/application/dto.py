"""DTOs de evidencias."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.shared.application.actor import ActorContext

from ..domain.value_objects import EvidenceType, FlowEntity


@dataclass(frozen=True)
class AttachEvidenceCommand:
    name: str
    description: str
    evidence_date: date
    evidence_type: EvidenceType
    path_or_url: str
    entity: FlowEntity
    entity_id: int
    actor: ActorContext
    mime_type: str | None = None
    size_bytes: int | None = None
    checksum_sha256: str | None = None


@dataclass(frozen=True)
class ReplaceEvidenceCommand:
    evidence_id: int
    path_or_url: str
    actor: ActorContext
    mime_type: str | None = None
    size_bytes: int | None = None
    checksum_sha256: str | None = None


@dataclass(frozen=True)
class LinkExistingEvidenceCommand:
    evidence_id: int
    entity: FlowEntity
    entity_id: int
    actor: ActorContext


@dataclass(frozen=True)
class UnlinkEvidenceCommand:
    evidence_id: int
    entity: FlowEntity
    entity_id: int
    actor: ActorContext
