"""Registro inmutable de auditoria."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class AuditEntry:
    id: int | UUID
    event_name: str
    occurred_at: datetime
    actor_id: int | None
    #: Nombre del autor al momento del movimiento. Se captura al escribir y no se
    #: recalcula: la bitacora debe conservar quien lo hizo aunque esa persona
    #: cambie de nombre o deje la institucion.
    actor_name: str | None
    aggregate_type: str
    aggregate_id: int | None
    action: str
    data: dict[str, Any]
