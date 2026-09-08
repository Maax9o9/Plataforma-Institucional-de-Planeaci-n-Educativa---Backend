"""Persistencia PostgreSQL de ejercicios POA."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.shared.domain.exceptions import ConflictError
from app.shared.infrastructure.db.unit_of_work import commit_or_flush, session_scope

from ..domain.entities import PoaExercise
from .models import PoaExerciseModel


class SqlAlchemyPoaRepository:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    async def add_exercise(self, item: PoaExercise) -> None:
        async with session_scope(self.session_factory) as session:
            try:
                model = PoaExerciseModel(anio=item.year)
                session.add(model)
                await commit_or_flush(session)
            except IntegrityError as exc:
                await session.rollback()
                raise ConflictError("El ejercicio POA ya existe.") from exc
            item.id = model.id

    async def get_exercise(self, item_id: int) -> PoaExercise | None:
        async with session_scope(self.session_factory) as session:
            model = await session.get(PoaExerciseModel, item_id)
            return PoaExercise(id=model.id, year=model.anio) if model else None

    async def list_exercises(self) -> list[PoaExercise]:
        async with session_scope(self.session_factory) as session:
            models = await session.scalars(select(PoaExerciseModel).order_by(PoaExerciseModel.anio))
            return [PoaExercise(id=model.id, year=model.anio) for model in models]
