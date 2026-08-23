"""Contrato de solo escritura y lectura para auditoria."""

from __future__ import annotations

from typing import Protocol

from ..entities import AuditEntry


class AuditRepository(Protocol):
    async def append(self, entry: AuditEntry) -> None: ...

    async def list(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        descending: bool = True,
        **filters,
    ) -> list[AuditEntry]: ...
