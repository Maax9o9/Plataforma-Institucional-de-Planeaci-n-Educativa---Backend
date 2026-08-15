"""DTOs internos de catalogos."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CreateAreaCommand:
    code: str
    name: str
    parent_id: int | None
    actor_id: int | None


@dataclass(frozen=True)
class CreateInstrumentCommand:
    code: str
    name: str
    description: str | None
    actor_id: int | None


@dataclass(frozen=True)
class UpdateAreaCommand:
    area_id: int
    code: str | None
    name: str | None
    parent_id: int | None
    actor_id: int


@dataclass(frozen=True)
class UpdateInstrumentCommand:
    instrument_id: int
    code: str | None
    name: str | None
    description: str | None
    actor_id: int


@dataclass(frozen=True)
class ChangeCatalogStatusCommand:
    item_id: int
    actor_id: int
