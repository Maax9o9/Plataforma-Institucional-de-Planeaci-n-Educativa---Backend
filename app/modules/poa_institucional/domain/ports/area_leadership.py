from __future__ import annotations

from typing import Protocol


class AreaLeadership(Protocol):
    async def has_person_in_charge(self, area_id: int) -> bool: ...
