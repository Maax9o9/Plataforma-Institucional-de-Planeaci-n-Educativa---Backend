"""Casos de uso separados para la estructura del POA."""

from __future__ import annotations

from app.shared.application.event_bus import EventBus
from app.shared.application.responsibility import ensure_operational_responsible
from app.shared.domain.exceptions import ForbiddenError, ResourceNotFoundError, ValidationError

from ....identity_access.domain.ports.user_repository import UserReader
from ....institutional_catalogs.domain.ports.repositories import AreaRepository
from ...domain.entities import PoaActivity, PoaExercise, PoaObjective, PoaProcess
from ...domain.events import PoaStructureChanged
from ...domain.ports.repositories import PoaRepository, ValidatedAdvanceReader
from ..dto import (
    CreateActivityCommand,
    CreateExerciseCommand,
    CreateObjectiveCommand,
    CreateProcessCommand,
    UpdateActivityCommand,
)


class CreateExercise:
    def __init__(self, repository: PoaRepository, event_bus: EventBus) -> None:
        self.repository = repository
        self.event_bus = event_bus

    async def execute(self, command: CreateExerciseCommand) -> PoaExercise:
        item = PoaExercise.create(command.year)
        await self.repository.add_exercise(item)
        await self.event_bus.publish(
            PoaStructureChanged(
                actor_id=command.actor_id,
                aggregate_type="poa_exercise",
                aggregate_id=item.id,
                action="created",
                data={"year": item.year},
            )
        )
        return item


class CreateProcess:
    def __init__(
        self, repository: PoaRepository, areas: AreaRepository, event_bus: EventBus
    ) -> None:
        self.repository = repository
        self.areas = areas
        self.event_bus = event_bus

    async def execute(self, command: CreateProcessCommand) -> PoaProcess:
        if await self.repository.get_exercise(command.exercise_id) is None:
            raise ResourceNotFoundError("El ejercicio POA no existe.")
        area = await self.areas.get_by_id(command.area_id)
        if area is None or not area.is_active:
            raise ValidationError("El area no existe o esta desactivada.")
        item = PoaProcess.create(
            exercise_id=command.exercise_id,
            name=command.name,
            area_id=command.area_id,
        )
        await self.repository.add_process(item)
        await self.event_bus.publish(
            PoaStructureChanged(
                actor_id=command.actor_id,
                aggregate_type="poa_process",
                aggregate_id=item.id,
                action="created",
                data={"exercise_id": item.exercise_id, "area_id": item.area_id},
            )
        )
        return item


class CreateObjective:
    def __init__(self, repository: PoaRepository, event_bus: EventBus) -> None:
        self.repository = repository
        self.event_bus = event_bus

    async def execute(self, command: CreateObjectiveCommand) -> PoaObjective:
        if await self.repository.get_process(command.process_id) is None:
            raise ResourceNotFoundError("El proceso POA no existe.")
        item = PoaObjective.create(
            process_id=command.process_id,
            poa_indicator=command.poa_indicator,
            objective=command.objective,
        )
        await self.repository.add_objective(item)
        await self.event_bus.publish(
            PoaStructureChanged(
                actor_id=command.actor_id,
                aggregate_type="poa_objective",
                aggregate_id=item.id,
                action="created",
                data={"process_id": item.process_id},
            )
        )
        return item


class CreateActivity:
    def __init__(self, repository: PoaRepository, users: UserReader, event_bus: EventBus) -> None:
        self.repository = repository
        self.users = users
        self.event_bus = event_bus

    async def execute(self, command: CreateActivityCommand) -> PoaActivity:
        objective = await self.repository.get_objective(command.objective_id)
        if objective is None:
            raise ResourceNotFoundError("El objetivo POA no existe.")
        process = await self.repository.get_process(objective.process_id)
        if process is None:
            raise ResourceNotFoundError("El proceso POA no existe.")
        if not command.actor.is_planning and command.actor.area_id != process.area_id:
            raise ForbiddenError("El objetivo POA no pertenece al area del usuario.")
        responsible = await self.users.get_by_id(command.responsible_id)
        ensure_operational_responsible(responsible, process.area_id)
        item = PoaActivity.create(
            objective_id=command.objective_id,
            description=command.description,
            unit=command.unit,
            annual_goal=command.annual_goal,
            observations=command.observations,
            responsible_id=command.responsible_id,
        )
        await self.repository.add_activity(item)
        await self.event_bus.publish(
            PoaStructureChanged(
                actor_id=command.actor.id,
                aggregate_type="poa_activity",
                aggregate_id=item.id,
                action="created",
                data={
                    "objective_id": item.objective_id,
                    "responsible_id": item.responsible_id,
                    "annual_goal": str(item.annual_goal),
                },
            )
        )
        return item


class UpdateActivity:
    def __init__(
        self,
        repository: PoaRepository,
        advances: ValidatedAdvanceReader,
        users: UserReader,
        event_bus: EventBus,
    ) -> None:
        self.repository = repository
        self.advances = advances
        self.users = users
        self.event_bus = event_bus

    async def execute(self, command: UpdateActivityCommand) -> PoaActivity:
        item = await self.repository.get_activity(command.activity_id)
        if item is None:
            raise ResourceNotFoundError("La actividad POA no existe.")
        objective = await self.repository.get_objective(item.objective_id)
        process = await self.repository.get_process(objective.process_id) if objective else None
        if process is None:
            raise ResourceNotFoundError("La estructura de la actividad POA no existe.")
        if not command.actor.is_planning and command.actor.area_id != process.area_id:
            raise ForbiddenError("La actividad POA no pertenece al area del usuario.")
        if command.annual_goal is not None and command.annual_goal != item.annual_goal:
            if await self.advances.has_validated_for_activity(item.id):
                raise ValidationError(
                    "La meta anual no puede modificarse despues de validar un cuatrimestre."
                )
        if command.responsible_id is not None:
            user = await self.users.get_by_id(command.responsible_id)
            ensure_operational_responsible(user, process.area_id)
        previous = {
            "description": item.description,
            "unit": item.unit,
            "annual_goal": str(item.annual_goal),
            "responsible_id": item.responsible_id,
        }
        item.update_details(
            description=command.description,
            unit=command.unit,
            annual_goal=command.annual_goal,
            observations=command.observations,
            responsible_id=command.responsible_id,
        )
        await self.repository.update_activity(item)
        await self.event_bus.publish(
            PoaStructureChanged(
                actor_id=command.actor.id,
                aggregate_type="poa_activity",
                aggregate_id=item.id,
                action="updated",
                data={
                    "previous": previous,
                    "current": {
                        "description": item.description,
                        "unit": item.unit,
                        "annual_goal": str(item.annual_goal),
                        "responsible_id": item.responsible_id,
                    },
                },
            )
        )
        return item
