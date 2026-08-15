"""Adaptador PostgreSQL de planeacion POA."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.domain.exceptions import ConflictError

from ..domain.entities import PoaActivity, PoaExercise, PoaObjective, PoaProcess
from .models import PoaActivityModel, PoaExerciseModel, PoaObjectiveModel, PoaProcessModel


class SqlAlchemyPoaRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def add_exercise(self, item: PoaExercise) -> None:
        async with self.session_factory() as session:
            try:
                model = PoaExerciseModel(anio=item.year)
                session.add(model)
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise ConflictError("El ejercicio POA ya existe.") from exc
        item.id = model.id

    async def add_process(self, item: PoaProcess) -> None:
        async with self.session_factory() as session:
            model = PoaProcessModel(
                ejercicio_id=item.exercise_id,
                nombre=item.name,
                area_id=item.area_id,
            )
            session.add(model)
            await session.commit()
        item.id = model.id

    async def add_objective(self, item: PoaObjective) -> None:
        async with self.session_factory() as session:
            model = PoaObjectiveModel(
                proceso_id=item.process_id,
                indicador_poa=item.poa_indicator,
                objetivo=item.objective,
            )
            session.add(model)
            await session.commit()
        item.id = model.id

    async def add_activity(self, item: PoaActivity) -> None:
        async with self.session_factory() as session:
            model = PoaActivityModel(
                objetivo_id=item.objective_id,
                descripcion=item.description,
                unidad_medida=item.unit,
                meta_anual=item.annual_goal,
                observaciones=item.observations,
                responsable_id=item.responsible_id,
            )
            session.add(model)
            await session.commit()
        item.id = model.id

    async def get_exercise(self, item_id: int) -> PoaExercise | None:
        async with self.session_factory() as session:
            model = await session.get(PoaExerciseModel, item_id)
            return PoaExercise(id=model.id, year=model.anio) if model else None

    async def get_process(self, item_id: int) -> PoaProcess | None:
        async with self.session_factory() as session:
            model = await session.get(PoaProcessModel, item_id)
            return (
                PoaProcess(
                    id=model.id,
                    exercise_id=model.ejercicio_id,
                    name=model.nombre,
                    area_id=model.area_id,
                )
                if model
                else None
            )

    async def get_objective(self, item_id: int) -> PoaObjective | None:
        async with self.session_factory() as session:
            model = await session.get(PoaObjectiveModel, item_id)
            return (
                PoaObjective(
                    id=model.id,
                    process_id=model.proceso_id,
                    poa_indicator=model.indicador_poa,
                    objective=model.objetivo,
                )
                if model
                else None
            )

    async def get_activity(self, item_id: int) -> PoaActivity | None:
        async with self.session_factory() as session:
            model = await session.get(PoaActivityModel, item_id)
            return self._activity(model) if model else None

    @staticmethod
    def _activity(model: PoaActivityModel) -> PoaActivity:
        return PoaActivity(
            id=model.id,
            objective_id=model.objetivo_id,
            description=model.descripcion,
            unit=model.unidad_medida,
            annual_goal=model.meta_anual,
            observations=model.observaciones,
            responsible_id=model.responsable_id,
            updated_at=datetime.now(UTC),
        )

    async def update_activity(self, item: PoaActivity) -> None:
        async with self.session_factory() as session:
            model = await session.get(PoaActivityModel, item.id)
            if model is None:
                return
            model.descripcion = item.description
            model.unidad_medida = item.unit
            model.meta_anual = item.annual_goal
            model.observaciones = item.observations
            model.responsable_id = item.responsible_id
            await session.commit()

    async def list_activities(self, *, area_id: int | None = None) -> list[PoaActivity]:
        async with self.session_factory() as session:
            statement = select(PoaActivityModel).order_by(PoaActivityModel.id)
            models = (await session.scalars(statement)).all()
            return [self._activity(model) for model in models]
