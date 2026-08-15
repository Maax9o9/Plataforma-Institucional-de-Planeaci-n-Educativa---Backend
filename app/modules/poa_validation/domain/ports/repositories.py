from typing import Protocol

from ....poa_tracking.domain.entities import PoaAdvance


class PoaAdvanceReader(Protocol):
    async def get_by_id(self, item_id: int) -> PoaAdvance | None: ...
    async def update(self, item: PoaAdvance) -> None: ...
