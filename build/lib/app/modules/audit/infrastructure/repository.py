"""Bitacora en memoria sin operaciones de update/delete."""

from __future__ import annotations

import asyncio
from datetime import datetime

from ..domain.entities import AuditEntry


class InMemoryAuditRepository:
    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []
        self._lock = asyncio.Lock()

    async def append(self, entry: AuditEntry) -> None:
        async with self._lock:
            self._entries.append(entry)

    async def list(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        actor_id: int | None = None,
        action: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        aggregate_type: str | None = None,
        aggregate_id: int | None = None,
        descending: bool = True,
    ) -> list[AuditEntry]:
        async with self._lock:
            entries = self._entries
            if actor_id is not None:
                entries = [item for item in entries if item.actor_id == actor_id]
            if action is not None:
                entries = [item for item in entries if item.action == action]
            if from_date is not None:
                entries = [item for item in entries if item.occurred_at >= from_date]
            if to_date is not None:
                entries = [item for item in entries if item.occurred_at <= to_date]
            if aggregate_type is not None:
                entries = [item for item in entries if item.aggregate_type == aggregate_type]
            if aggregate_id is not None:
                entries = [item for item in entries if item.aggregate_id == aggregate_id]
            entries = sorted(
                entries,
                key=lambda item: (item.occurred_at, str(item.id)),
                reverse=descending,
            )
            return list(entries[offset : offset + limit])

    async def count(self, **filters) -> int:
        entries = await self.list(offset=0, limit=max(len(self._entries), 1), **filters)
        return len(entries)
