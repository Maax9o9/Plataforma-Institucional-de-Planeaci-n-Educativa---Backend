"""Casos de uso separados para la estructura del POA."""

from __future__ import annotations

from app.shared.application.event_bus import EventBus
from app.shared.domain.exceptions import ResourceNotFoundError, ValidationError

from ....identity_access.domain.ports.user_repository import UserReader
from ....institutional_catalogs.domain.ports.repositories import AreaRepository
from ...domain.entities import PoaActivity, PoaExercise, PoaObjective, PoaProcess
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
        return item


class CreateActivity:
    def __init__(self, repository: PoaRepository, users: UserReader, event_bus: EventBus) -> None:
        self.repository = repository
        self.users = users
        self.event_bus = event_bus

    async def execute(self, command: CreateActivityCommand) -> PoaActivity:
        if await self.repository.get_objective(command.objective_id) is None:
            raise ResourceNotFoundError("El objetivo POA no existe.")
        responsible = await self.users.get_by_id(command.responsible_id)
        if responsible is None or not responsible.is_active:
            raise ValidationError("El responsable no existe o esta desactivado.")
        item = PoaActivity.create(
            objective_id=command.objective_id,
            description=command.description,
            unit=command.unit,
            annual_goal=command.annual_goal,
            observations=command.observations,
            responsible_id=command.responsible_id,
        )
        await self.repository.add_activity(item)
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
        if command.annual_goal is not None and command.annual_goal != item.annual_goal:
            if await self.advances.has_validated_for_activity(item.id):
                raise ValidationError(
                    "La meta anual no puede modificarse despues de validar un cuatrimestre."
                )
        if command.responsible_id is not None:
            user = await self.users.get_by_id(command.responsible_id)
            if user is None or not user.is_active:
                raise ValidationError("El responsable no existe o esta desactivado.")
        item.update_details(
            description=command.description,
            unit=command.unit,
            annual_goal=command.annual_goal,
            observations=command.observations,
            responsible_id=command.responsible_id,
        )
        await self.repository.update_activity(item)
        return item
