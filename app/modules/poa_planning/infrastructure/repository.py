"""Persistencia en memoria de ejercicios POA."""

from itertools import count

from app.shared.domain.exceptions import ConflictError, ResourceNotFoundError

from ..domain.entities import PoaExercise


class InMemoryPoaRepository:
    def __init__(self) -> None:
        self.exercises: dict[int, PoaExercise] = {}
        self._next_id = count(1)

    async def add_exercise(self, item: PoaExercise) -> None:
        if any(current.year == item.year for current in self.exercises.values()):
            raise ConflictError("El ejercicio POA ya existe.")
        item.id = next(self._next_id)
        self.exercises[item.id] = item

    async def get_exercise(self, item_id: int) -> PoaExercise | None:
        return self.exercises.get(item_id)

    async def list_exercises(self) -> list[PoaExercise]:
        return sorted(self.exercises.values(), key=lambda item: item.year)

    async def update_exercise(self, item: PoaExercise) -> None:
        if item.id not in self.exercises:
            raise ResourceNotFoundError("El ejercicio POA no existe.")
        self.exercises[item.id] = item
