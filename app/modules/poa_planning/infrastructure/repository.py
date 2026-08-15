"""Repositorio en memoria de planeacion POA."""

from __future__ import annotations

from itertools import count

from ..domain.entities import PoaActivity, PoaExercise, PoaObjective, PoaProcess


class InMemoryPoaRepository:
    def __init__(self) -> None:
        self.exercises: dict[int, PoaExercise] = {}
        self.processes: dict[int, PoaProcess] = {}
        self.objectives: dict[int, PoaObjective] = {}
        self.activities: dict[int, PoaActivity] = {}
        self._next_id = count(1)

    def _assign(self, item) -> None:
        if item.id == 0:
            item.id = next(self._next_id)

    async def add_exercise(self, item: PoaExercise) -> None:
        self._assign(item)
        self.exercises[item.id] = item

    async def add_process(self, item: PoaProcess) -> None:
        self._assign(item)
        self.processes[item.id] = item

    async def add_objective(self, item: PoaObjective) -> None:
        self._assign(item)
        self.objectives[item.id] = item

    async def add_activity(self, item: PoaActivity) -> None:
        self._assign(item)
        self.activities[item.id] = item

    async def get_exercise(self, item_id: int) -> PoaExercise | None:
        return self.exercises.get(item_id)

    async def get_process(self, item_id: int) -> PoaProcess | None:
        return self.processes.get(item_id)

    async def get_objective(self, item_id: int) -> PoaObjective | None:
        return self.objectives.get(item_id)

    async def get_activity(self, item_id: int) -> PoaActivity | None:
        return self.activities.get(item_id)

    async def update_activity(self, item: PoaActivity) -> None:
        self.activities[item.id] = item

    async def list_activities(self, *, area_id: int | None = None) -> list[PoaActivity]:
        if area_id is None:
            return list(self.activities.values())
        process_ids = {item.id for item in self.processes.values() if item.area_id == area_id}
        objective_ids = {
            item.id for item in self.objectives.values() if item.process_id in process_ids
        }
        return [item for item in self.activities.values() if item.objective_id in objective_ids]
