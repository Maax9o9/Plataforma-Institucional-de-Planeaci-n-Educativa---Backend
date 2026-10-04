"""Puerto de persistencia para catálogos, cédulas y emisiones POA."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from ..cedula_entities import (
    PoaActivityCatalog,
    PoaActivityFollowUp,
    PoaFollowUpCard,
    PoaForm,
    PoaFormActivity,
    PoaFormDetail,
    PoaFormIndicator,
    PoaFormIssue,
    PoaFormQuarter,
    PoaIndicatorCatalog,
    PoaObjectiveCatalog,
    PoaStrategyCatalog,
)


class PoaFormRepository(Protocol):
    async def ensure_catalogs(self) -> None: ...

    async def list_objectives(self) -> list[PoaObjectiveCatalog]: ...

    async def list_strategies(
        self, *, objective_number: int | None = None
    ) -> list[PoaStrategyCatalog]: ...

    async def get_strategy(self, key: str) -> PoaStrategyCatalog | None: ...

    async def list_indicators(
        self, *, objective_number: int | None = None
    ) -> list[PoaIndicatorCatalog]: ...

    async def get_indicator(self, key: str) -> PoaIndicatorCatalog | None: ...

    async def list_activity_catalog(
        self, *, strategy_key: str | None = None
    ) -> list[PoaActivityCatalog]: ...

    async def get_activity_catalog(self, key: str) -> PoaActivityCatalog | None: ...

    async def add_form(self, item: PoaForm) -> None: ...

    async def get_form(self, item_id: int) -> PoaForm | None: ...

    async def update_form(self, item: PoaForm) -> None: ...

    async def delete_form(self, item_id: int) -> None: ...

    async def add_form_quarter(self, item: PoaFormQuarter) -> None: ...

    async def list_form_quarters(self, form_id: int) -> list[PoaFormQuarter]: ...

    async def list_forms(
        self,
        *,
        exercise_id: int | None = None,
        objective_number: int | None = None,
        responsible_area_id: int | None = None,
    ) -> list[PoaForm]: ...

    async def add_form_indicator(self, item: PoaFormIndicator) -> None: ...

    async def get_form_indicator(self, item_id: int) -> PoaFormIndicator | None: ...

    async def update_form_indicator(self, item: PoaFormIndicator) -> None: ...

    async def delete_form_indicator(self, item_id: int) -> None: ...

    async def add_form_activity(self, item: PoaFormActivity) -> None: ...

    async def get_form_activity(self, item_id: int) -> PoaFormActivity | None: ...

    async def update_form_activity(self, item: PoaFormActivity) -> None: ...

    async def delete_form_activity(self, item_id: int) -> None: ...

    async def replace_activity_criteria(
        self, form_activity_id: int, criteria_seaes_ids: tuple[int, ...], updated_at: datetime
    ) -> None: ...

    async def get_follow_up(self, item_id: int) -> PoaActivityFollowUp | None: ...

    async def get_follow_up_by_quarter(
        self, form_activity_id: int, quarter: int
    ) -> PoaActivityFollowUp | None: ...

    async def list_follow_up_cards(
        self,
        *,
        exercise_id: int | None = None,
        quarter: int | None = None,
        executing_area_id: int | None = None,
        status: str | None = None,
        offset: int = 0,
        limit: int = 200,
    ) -> tuple[list[PoaFollowUpCard], int]: ...

    async def update_follow_up(self, item: PoaActivityFollowUp) -> None: ...

    async def upsert_follow_up(self, item: PoaActivityFollowUp) -> PoaActivityFollowUp: ...

    async def get_detail(self, form_id: int) -> PoaFormDetail | None: ...

    async def add_issue(self, item: PoaFormIssue) -> None: ...

    async def list_issues(self, form_id: int) -> list[PoaFormIssue]: ...

    async def get_issue(self, issue_id: int) -> PoaFormIssue | None: ...
