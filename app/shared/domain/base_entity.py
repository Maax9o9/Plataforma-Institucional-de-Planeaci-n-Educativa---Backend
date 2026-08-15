"""Entidad base independiente de ORM y de frameworks HTTP."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(kw_only=True)
class BaseEntity:
    id: int = field(default=0)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def touch(self) -> None:
        self.updated_at = utc_now()
