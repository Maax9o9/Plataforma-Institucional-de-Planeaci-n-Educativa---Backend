"""Repositorio en memoria para cédulas institucionales POA."""

from __future__ import annotations

from itertools import count

from app.shared.domain.exceptions import ConflictError

from ..domain.cedula_entities import (
    PoaActivityCatalog,
    PoaActivityFollowUp,
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
from .reference_data import (
    POA_ACTIVITIES,
    POA_INDICATORS,
    POA_OBJECTIVES,
    POA_STRATEGIES,
)


class InMemoryPoaFormRepository:
    def __init__(self) -> None:
        self.objectives = {
            int(item["numero"]): PoaObjectiveCatalog(
                key=str(item["clave"]),
                number=int(item["numero"]),
                denomination=str(item["denominacion"]),
            )
            for item in POA_OBJECTIVES
        }
        self.strategies = {
            str(item["clave"]): PoaStrategyCatalog(
                key=str(item["clave"]),
                objective_number=int(item["objetivo_numero"]),
                denomination=str(item["denominacion"]),
            )
            for item in POA_STRATEGIES
        }
        self.indicators = {
            str(item["clave"]): PoaIndicatorCatalog(
                key=str(item["clave"]),
                objective_number=int(item["objetivo_numero"]),
                name=str(item["nombre"]),
                formula=str(item["formula"]),
                unit=str(item["unidad_medida"]),
            )
            for item in POA_INDICATORS
        }
        self.activity_catalog = {
            str(item["clave"]): PoaActivityCatalog(
                key=str(item["clave"]),
                strategy_key=str(item["estrategia_clave"]),
                description=str(item["descripcion"]),
            )
            for item in POA_ACTIVITIES
        }
        self.forms: dict[int, PoaForm] = {}
        self.form_indicators: dict[int, PoaFormIndicator] = {}
        self.form_quarters: dict[int, PoaFormQuarter] = {}
        self.form_activities: dict[int, PoaFormActivity] = {}
        self.follow_ups: dict[int, PoaActivityFollowUp] = {}
        self.issues: dict[int, PoaFormIssue] = {}
        self._form_ids = count(1)
        self._indicator_ids = count(1)
        self._quarter_ids = count(1)
        self._activity_ids = count(1)
        self._follow_up_ids = count(1)
        self._issue_ids = count(1)

    async def ensure_catalogs(self) -> None:
        return None

    async def list_objectives(self) -> list[PoaObjectiveCatalog]:
        return sorted(self.objectives.values(), key=lambda item: item.number)

    async def list_strategies(
        self, *, objective_number: int | None = None
    ) -> list[PoaStrategyCatalog]:
        items = self.strategies.values()
        if objective_number is not None:
            items = [item for item in items if item.objective_number == objective_number]
        return sorted(items, key=lambda item: tuple(map(int, item.key.split("."))))

    async def get_strategy(self, key: str) -> PoaStrategyCatalog | None:
        return self.strategies.get(key)

    async def list_indicators(
        self, *, objective_number: int | None = None
    ) -> list[PoaIndicatorCatalog]:
        items = self.indicators.values()
        if objective_number is not None:
            items = [item for item in items if item.objective_number == objective_number]
        return sorted(items, key=lambda item: tuple(map(int, item.key.split("."))))

    async def get_indicator(self, key: str) -> PoaIndicatorCatalog | None:
        return self.indicators.get(key)

    async def list_activity_catalog(
        self, *, strategy_key: str | None = None
    ) -> list[PoaActivityCatalog]:
        items = self.activity_catalog.values()
        if strategy_key is not None:
            items = [item for item in items if item.strategy_key == strategy_key]
        return sorted(items, key=lambda item: tuple(map(int, item.key.split("."))))

    async def get_activity_catalog(self, key: str) -> PoaActivityCatalog | None:
        return self.activity_catalog.get(key)

    async def add_form(self, item: PoaForm) -> None:
        duplicate = any(
            existing.exercise_id == item.exercise_id
            and existing.strategy_key == item.strategy_key
            and existing.responsible_area_id == item.responsible_area_id
            for existing in self.forms.values()
        )
        if duplicate:
            raise ConflictError("Ya existe una cédula para la estrategia, área y ejercicio.")
        item.id = next(self._form_ids)
        self.forms[item.id] = item

    async def get_form(self, item_id: int) -> PoaForm | None:
        return self.forms.get(item_id)

    async def update_form(self, item: PoaForm) -> None:
        item.version += 1
        self.forms[item.id] = item

    async def add_form_quarter(self, item: PoaFormQuarter) -> None:
        if any(
            current.form_id == item.form_id and current.quarter == item.quarter
            for current in self.form_quarters.values()
        ):
            raise ConflictError("El cuatrimestre ya está configurado para la cédula.")
        item.id = next(self._quarter_ids)
        self.form_quarters[item.id] = item

    async def list_form_quarters(self, form_id: int) -> list[PoaFormQuarter]:
        return sorted(
            [item for item in self.form_quarters.values() if item.form_id == form_id],
            key=lambda item: item.quarter,
        )

    async def list_forms(
        self,
        *,
        exercise_id: int | None = None,
        objective_number: int | None = None,
        responsible_area_id: int | None = None,
    ) -> list[PoaForm]:
        items = list(self.forms.values())
        if exercise_id is not None:
            items = [item for item in items if item.exercise_id == exercise_id]
        if objective_number is not None:
            items = [item for item in items if item.objective_number == objective_number]
        if responsible_area_id is not None:
            items = [item for item in items if item.responsible_area_id == responsible_area_id]
        return sorted(items, key=lambda item: item.id)

    async def add_form_indicator(self, item: PoaFormIndicator) -> None:
        if any(
            existing.form_id == item.form_id and existing.indicator_key == item.indicator_key
            for existing in self.form_indicators.values()
        ):
            raise ConflictError("El indicador ya está asociado a la cédula.")
        item.id = next(self._indicator_ids)
        self.form_indicators[item.id] = item

    async def get_form_indicator(self, item_id: int) -> PoaFormIndicator | None:
        return self.form_indicators.get(item_id)

    async def update_form_indicator(self, item: PoaFormIndicator) -> None:
        self.form_indicators[item.id] = item

    async def add_form_activity(self, item: PoaFormActivity) -> None:
        if any(
            existing.form_id == item.form_id and existing.activity_key == item.activity_key
            for existing in self.form_activities.values()
        ):
            raise ConflictError("La actividad ya está asociada a la cédula.")
        item.id = next(self._activity_ids)
        self.form_activities[item.id] = item

    async def get_form_activity(self, item_id: int) -> PoaFormActivity | None:
        return self.form_activities.get(item_id)

    async def update_form_activity(self, item: PoaFormActivity) -> None:
        self.form_activities[item.id] = item

    async def get_follow_up(self, item_id: int) -> PoaActivityFollowUp | None:
        return self.follow_ups.get(item_id)

    async def update_follow_up(self, item: PoaActivityFollowUp) -> None:
        self.follow_ups[item.id] = item

    async def upsert_follow_up(self, item: PoaActivityFollowUp) -> PoaActivityFollowUp:
        existing = next(
            (
                current
                for current in self.follow_ups.values()
                if current.form_activity_id == item.form_activity_id
                and current.quarter == item.quarter
            ),
            None,
        )
        if existing is not None:
            item.id = existing.id
            item.created_at = existing.created_at
        else:
            item.id = next(self._follow_up_ids)
        self.follow_ups[item.id] = item
        return item

    async def get_detail(self, form_id: int) -> PoaFormDetail | None:
        form = self.forms.get(form_id)
        if form is None:
            return None
        activities = [item for item in self.form_activities.values() if item.form_id == form_id]
        activity_ids = {item.id for item in activities}
        return PoaFormDetail(
            form=form,
            quarters=await self.list_form_quarters(form_id),
            indicators=[item for item in self.form_indicators.values() if item.form_id == form_id],
            activities=activities,
            follow_ups=[
                item for item in self.follow_ups.values() if item.form_activity_id in activity_ids
            ],
        )

    async def add_issue(self, item: PoaFormIssue) -> None:
        if any(
            existing.form_id == item.form_id and existing.quarter == item.quarter
            for existing in self.issues.values()
        ):
            raise ConflictError("La cédula ya fue emitida para ese cuatrimestre.")
        item.id = next(self._issue_ids)
        self.issues[item.id] = item

    async def list_issues(self, form_id: int) -> list[PoaFormIssue]:
        return sorted(
            [item for item in self.issues.values() if item.form_id == form_id],
            key=lambda item: item.quarter,
        )

    async def get_issue(self, issue_id: int) -> PoaFormIssue | None:
        return self.issues.get(issue_id)
