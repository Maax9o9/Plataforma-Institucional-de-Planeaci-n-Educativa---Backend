"""Edicion, desactivacion y configuracion complementaria de indicadores."""

from __future__ import annotations

from decimal import Decimal

from app.shared.application.event_bus import EventBus
from app.shared.application.responsibility import ensure_operational_responsible
from app.shared.domain.exceptions import ConflictError, ResourceNotFoundError

from ...domain.entities import Baseline, Goal, Indicator
from ...domain.events import (
    IndicatorBaselineCreated,
    IndicatorDeactivated,
    IndicatorGoalCreated,
    IndicatorPeriodicityChanged,
    IndicatorUpdated,
)
from ...domain.ports.repositories import IndicatorRepository, ReferenceReader
from ..dto import (
    ChangeIndicatorStatusCommand,
    ChangePeriodicityCommand,
    CreateBaselineCommand,
    CreateGoalCommand,
    UpdateIndicatorCommand,
)


def _json_value(value):
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, Decimal):
        return str(value)
    return value


class UpdateIndicator:
    def __init__(
        self,
        repository: IndicatorRepository,
        area_reader: ReferenceReader,
        user_reader: ReferenceReader,
        event_bus: EventBus,
    ) -> None:
        self.repository = repository
        self.area_reader = area_reader
        self.user_reader = user_reader
        self.event_bus = event_bus

    async def execute(self, command: UpdateIndicatorCommand) -> Indicator:
        indicator = await self.repository.get_by_id(command.indicator_id)
        if indicator is None:
            raise ResourceNotFoundError("El indicador no existe.")
        if (
            command.expected_version is not None
            and command.expected_version != indicator.version
        ):
            raise ConflictError("El indicador fue modificado por otro usuario.")
        previous = {
            key: getattr(indicator, key) for key in command.changes if hasattr(indicator, key)
        }
        if "key" in command.changes and command.changes["key"] != indicator.key:
            duplicate = await self.repository.get_by_key(command.changes["key"])
            if duplicate and duplicate.id != indicator.id:
                raise ConflictError("Ya existe un indicador con esa clave.")
        if "area_id" in command.changes:
            area = await self.area_reader.get_by_id(command.changes["area_id"])
            if area is None or not area.is_active:
                from app.shared.domain.exceptions import ValidationError

                raise ValidationError("El area no existe o esta desactivada.")
        if "responsible_id" in command.changes or "area_id" in command.changes:
            responsible_id = command.changes.get("responsible_id", indicator.responsible_id)
            area_id = command.changes.get("area_id", indicator.area_id)
            user = await self.user_reader.get_by_id(responsible_id)
            ensure_operational_responsible(user, area_id)
        indicator.update(**command.changes)
        await self.repository.update(indicator)
        await self.event_bus.publish(
            IndicatorUpdated(
                actor_id=command.actor_id,
                aggregate_type="indicator",
                aggregate_id=indicator.id,
                action="updated",
                data={
                    "previous": {key: _json_value(value) for key, value in previous.items()},
                    "current": {key: _json_value(getattr(indicator, key)) for key in previous},
                },
            )
        )
        return indicator


class DeactivateIndicator:
    def __init__(self, repository: IndicatorRepository, event_bus: EventBus) -> None:
        self.repository = repository
        self.event_bus = event_bus

    async def execute(self, command: ChangeIndicatorStatusCommand) -> Indicator:
        indicator = await self.repository.get_by_id(command.indicator_id)
        if indicator is None:
            raise ResourceNotFoundError("El indicador no existe.")
        indicator.deactivate()
        await self.repository.update(indicator)
        await self.event_bus.publish(
            IndicatorDeactivated(
                actor_id=command.actor_id,
                aggregate_type="indicator",
                aggregate_id=indicator.id,
                action="deactivated",
                data={"key": indicator.key},
            )
        )
        return indicator


class CreateBaseline:
    def __init__(self, repository: IndicatorRepository, event_bus: EventBus) -> None:
        self.repository = repository
        self.event_bus = event_bus

    async def execute(self, command: CreateBaselineCommand) -> Baseline:
        if await self.repository.get_by_id(command.indicator_id) is None:
            raise ResourceNotFoundError("El indicador no existe.")
        baseline = Baseline(
            indicator_id=command.indicator_id,
            year=command.year,
            period=command.period,
            value=command.value,
        )
        await self.repository.add_baseline(baseline)
        await self.event_bus.publish(
            IndicatorBaselineCreated(
                actor_id=command.actor_id,
                aggregate_type="indicator",
                aggregate_id=command.indicator_id,
                action="baseline_created",
                data={"year": command.year, "value": str(command.value)},
            )
        )
        return baseline


class CreateGoal:
    def __init__(
        self,
        repository: IndicatorRepository,
        period_reader: ReferenceReader,
        event_bus: EventBus,
    ) -> None:
        self.repository = repository
        self.period_reader = period_reader
        self.event_bus = event_bus

    async def execute(self, command: CreateGoalCommand) -> Goal:
        indicator = await self.repository.get_by_id(command.indicator_id)
        if indicator is None:
            raise ResourceNotFoundError("El indicador no existe.")
        period = await self.period_reader.get_by_id(command.period_id)
        if period is None:
            raise ResourceNotFoundError("El periodo no existe.")
        if period.period_type.value != "indicadores":
            raise ConflictError("La meta requiere un periodo de indicadores.")
        if period.periodicity != indicator.periodicity:
            raise ConflictError("La periodicidad de la meta no coincide con el indicador.")
        if period.status.value != "borrador":
            raise ConflictError("Las metas deben registrarse antes de abrir el periodo.")
        if command.value < 0:
            raise ConflictError("La meta no puede ser negativa.")
        goal = Goal(
            indicator_id=command.indicator_id,
            period_id=command.period_id,
            value=command.value,
        )
        await self.repository.add_goal(goal)
        await self.event_bus.publish(
            IndicatorGoalCreated(
                actor_id=command.actor_id,
                aggregate_type="indicator",
                aggregate_id=command.indicator_id,
                action="goal_created",
                data={"period_id": command.period_id, "value": str(command.value)},
            )
        )
        return goal


class ChangeIndicatorPeriodicity:
    def __init__(self, repository: IndicatorRepository, event_bus: EventBus) -> None:
        self.repository = repository
        self.event_bus = event_bus

    async def execute(self, command: ChangePeriodicityCommand) -> Indicator:
        indicator = await self.repository.get_by_id(command.indicator_id)
        if indicator is None:
            raise ResourceNotFoundError("El indicador no existe.")
        previous = indicator.periodicity.value
        indicator.set_periodicity(command.periodicity)
        await self.repository.update(indicator)
        await self.event_bus.publish(
            IndicatorPeriodicityChanged(
                actor_id=command.actor_id,
                aggregate_type="indicator",
                aggregate_id=indicator.id,
                action="periodicity_changed",
                data={"previous": previous, "current": command.periodicity.value},
            )
        )
        return indicator
