"""Puerto de persistencia para catálogos, cédulas y emisiones POA."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from ..cedula_entities import (
    PoaActivityCatalog,
    PoaActivityFollowUp,
    PoaCatalogo,
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
    #: Siembra el POA inicial -con su catálogo- si todavía no hay ninguno, y
    #: devuelve su id. Si ya hay POA no toca nada: el catálogo es
    #: administrable y resembrarlo resucitaría lo que Planeación retiró.
    async def ensure_catalogs(self) -> int: ...

    async def list_catalogs(self) -> list[PoaCatalogo]: ...

    async def get_catalog(self, catalog_id: int) -> PoaCatalogo | None: ...

    #: El nombre del POA es único: es con lo que Planeación lo distingue en el
    #: selector, y por eso se puede buscar por él.
    async def get_catalog_by_name(self, name: str) -> PoaCatalogo | None: ...

    async def save_catalog(self, item: PoaCatalogo) -> PoaCatalogo: ...

    #: Mueve la «última modificación» del POA. La llama quien cambia el
    #: contenido del catálogo, no quien renombra el POA.
    async def touch_catalog(self, catalog_id: int) -> None: ...

    async def list_objectives(
        self, *, catalog_id: int, only_active: bool = False
    ) -> list[PoaObjectiveCatalog]: ...

    async def get_objective(self, catalog_id: int, number: int) -> PoaObjectiveCatalog | None: ...

    #: Alta o edición del catálogo. Es un upsert: quién puede crear y quién
    #: editar lo decide el caso de uso, no el repositorio. De qué POA cuelga
    #: lo trae la entidad en su `catalog_id`.
    async def save_objective(self, item: PoaObjectiveCatalog) -> PoaObjectiveCatalog: ...

    async def save_strategy(self, item: PoaStrategyCatalog) -> PoaStrategyCatalog: ...

    async def save_indicator(self, item: PoaIndicatorCatalog) -> PoaIndicatorCatalog: ...

    async def save_activity_catalog(self, item: PoaActivityCatalog) -> PoaActivityCatalog: ...

    async def list_strategies(
        self,
        *,
        catalog_id: int,
        objective_number: int | None = None,
        only_active: bool = False,
    ) -> list[PoaStrategyCatalog]: ...

    async def get_strategy(self, catalog_id: int, key: str) -> PoaStrategyCatalog | None: ...

    async def list_indicators(
        self,
        *,
        catalog_id: int,
        objective_number: int | None = None,
        only_active: bool = False,
    ) -> list[PoaIndicatorCatalog]: ...

    async def get_indicator(self, catalog_id: int, key: str) -> PoaIndicatorCatalog | None: ...

    async def list_activity_catalog(
        self,
        *,
        catalog_id: int,
        strategy_key: str | None = None,
        only_active: bool = False,
    ) -> list[PoaActivityCatalog]: ...

    async def get_activity_catalog(
        self, catalog_id: int, key: str
    ) -> PoaActivityCatalog | None: ...

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
