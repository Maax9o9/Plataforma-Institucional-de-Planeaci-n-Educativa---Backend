"""Persistencia PostgreSQL de ejercicios POA."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.shared.domain.exceptions import ConflictError, ResourceNotFoundError
from app.shared.infrastructure.db.unit_of_work import commit_or_flush, session_scope

from ..domain.entities import PoaExercise
from ..domain.value_objects import PoaExerciseStatus
from .models import PoaExerciseModel


def _to_entity(model: PoaExerciseModel) -> PoaExercise:
    return PoaExercise(
        id=model.id,
        year=model.anio,
        status=PoaExerciseStatus(model.estado),
        formulation_deadline=model.fecha_limite_formulacion,
        review_comment=model.comentario_revision,
        closed_at=model.cerrado_en,
    )


class SqlAlchemyPoaRepository:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    async def add_exercise(self, item: PoaExercise) -> None:
        async with session_scope(self.session_factory) as session:
            try:
                model = PoaExerciseModel(
                    anio=item.year,
                    estado=item.status.value,
                    fecha_limite_formulacion=item.formulation_deadline,
                    comentario_revision=item.review_comment,
                    cerrado_en=item.closed_at,
                )
                session.add(model)
                await commit_or_flush(session)
            except IntegrityError as exc:
                await session.rollback()
                raise ConflictError("El ejercicio POA ya existe.") from exc
            item.id = model.id

    async def get_exercise(self, item_id: int) -> PoaExercise | None:
        async with session_scope(self.session_factory) as session:
            model = await session.get(PoaExerciseModel, item_id)
            return _to_entity(model) if model else None

    async def list_exercises(self) -> list[PoaExercise]:
        async with session_scope(self.session_factory) as session:
            models = await session.scalars(
                select(PoaExerciseModel).order_by(PoaExerciseModel.anio)
            )
            return [_to_entity(model) for model in models]

    async def update_exercise(self, item: PoaExercise) -> None:
        async with session_scope(self.session_factory) as session:
            model = await session.get(PoaExerciseModel, item.id)
            if model is None:
                raise ResourceNotFoundError("El ejercicio POA no existe.")
            model.estado = item.status.value
            model.fecha_limite_formulacion = item.formulation_deadline
            model.comentario_revision = item.review_comment
            model.cerrado_en = item.closed_at
            await commit_or_flush(session)
