"""Adaptador PostgreSQL del catalogo maestro."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.domain.exceptions import ConflictError

from ..domain.entities import Baseline, Goal, Indicator
from ..domain.value_objects import IndicatorPeriodicity
from .models import (
    BaselineModel,
    GoalModel,
    IndicatorCriteriaModel,
    IndicatorInstrumentModel,
    IndicatorModel,
)


class SqlAlchemyIndicatorRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def _instruments_for(self, session: AsyncSession, indicator_id: int) -> set[int]:
        result = await session.execute(
            select(IndicatorInstrumentModel.c.instrumento_id).where(
                IndicatorInstrumentModel.c.indicador_id == indicator_id
            )
        )
        return set(result.scalars().all())

    async def _criteria_for(self, session: AsyncSession, indicator_id: int) -> set[int]:
        result = await session.execute(
            select(IndicatorCriteriaModel.c.criterio_seaes_id).where(
                IndicatorCriteriaModel.c.indicador_id == indicator_id
            )
        )
        return set(result.scalars().all())

    async def _to_domain(self, session: AsyncSession, model: IndicatorModel) -> Indicator:
        return Indicator(
            id=model.id,
            key=model.clave,
            name=model.nombre,
            calculation_method=model.metodo_calculo,
            unit=model.unidad_medida,
            definition=model.definicion,
            dimension=model.dimension,
            verification_document=model.documento_verificacion,
            information_source=model.fuente_informacion,
            methodological_notes=model.observaciones_metodologicas,
            indicator_type_id=model.tipo_indicador_id,
            area_id=model.area_id,
            responsible_id=model.responsable_id,
            periodicity=IndicatorPeriodicity(model.periodicidad),
            green_threshold=model.umbral_verde_min,
            yellow_threshold=model.umbral_amarillo_min,
            is_active=model.activo,
            instrument_ids=await self._instruments_for(session, model.id),
            criteria_ids=await self._criteria_for(session, model.id),
            created_at=model.creado_en,
            updated_at=model.actualizado_en,
        )

    async def add(self, indicator: Indicator) -> None:
        now = datetime.now(UTC)
        async with self.session_factory() as session:
            try:
                model = IndicatorModel(
                    clave=indicator.key,
                    nombre=indicator.name,
                    definicion=indicator.definition,
                    metodo_calculo=indicator.calculation_method,
                    unidad_medida=indicator.unit,
                    dimension=indicator.dimension,
                    documento_verificacion=indicator.verification_document,
                    fuente_informacion=indicator.information_source,
                    observaciones_metodologicas=indicator.methodological_notes,
                    tipo_indicador_id=indicator.indicator_type_id,
                    area_id=indicator.area_id,
                    responsable_id=indicator.responsible_id,
                    periodicidad=indicator.periodicity.value,
                    umbral_verde_min=indicator.green_threshold,
                    umbral_amarillo_min=indicator.yellow_threshold,
                    activo=indicator.is_active,
                    creado_en=now,
                    actualizado_en=now,
                )
                session.add(model)
                await session.flush()
                if indicator.instrument_ids:
                    await session.execute(
                        insert(IndicatorInstrumentModel),
                        [
                            {"indicador_id": model.id, "instrumento_id": item_id}
                            for item_id in indicator.instrument_ids
                        ],
                    )
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise ConflictError(
                    "No se pudo registrar el indicador por una referencia duplicada o invalida."
                ) from exc
        indicator.id = model.id
        indicator.created_at = now
        indicator.updated_at = now

    async def get_by_id(self, indicator_id: int) -> Indicator | None:
        async with self.session_factory() as session:
            model = await session.get(IndicatorModel, indicator_id)
            return await self._to_domain(session, model) if model else None

    async def get_by_key(self, key: str) -> Indicator | None:
        async with self.session_factory() as session:
            model = (
                await session.execute(
                    select(IndicatorModel).where(IndicatorModel.clave == key.strip().upper())
                )
            ).scalar_one_or_none()
            return await self._to_domain(session, model) if model else None

    async def list(self, *, active_only: bool = False) -> list[Indicator]:
        async with self.session_factory() as session:
            statement = select(IndicatorModel).order_by(IndicatorModel.clave)
            if active_only:
                statement = statement.where(IndicatorModel.activo.is_(True))
            models = (await session.scalars(statement)).all()
            indicators = [await self._to_domain(session, model) for model in models]
            return indicators

    async def update(self, indicator: Indicator) -> None:
        async with self.session_factory() as session:
            try:
                model = await session.get(IndicatorModel, indicator.id)
                if model is None:
                    return
                model.clave = indicator.key
                model.nombre = indicator.name
                model.definicion = indicator.definition
                model.metodo_calculo = indicator.calculation_method
                model.unidad_medida = indicator.unit
                model.dimension = indicator.dimension
                model.documento_verificacion = indicator.verification_document
                model.fuente_informacion = indicator.information_source
                model.observaciones_metodologicas = indicator.methodological_notes
                model.tipo_indicador_id = indicator.indicator_type_id
                model.area_id = indicator.area_id
                model.responsable_id = indicator.responsible_id
                model.periodicidad = indicator.periodicity.value
                model.umbral_verde_min = indicator.green_threshold
                model.umbral_amarillo_min = indicator.yellow_threshold
                model.activo = indicator.is_active
                model.actualizado_en = indicator.updated_at
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise ConflictError("No se pudo actualizar el indicador.") from exc

    async def add_baseline(self, baseline: Baseline) -> None:
        async with self.session_factory() as session:
            try:
                session.add(
                    BaselineModel(
                        indicador_id=baseline.indicator_id,
                        anio=baseline.year,
                        periodo=baseline.period,
                        valor=baseline.value,
                        creado_en=datetime.now(UTC),
                    )
                )
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise ConflictError("El indicador ya tiene una linea base.") from exc

    async def add_goal(self, goal: Goal) -> None:
        async with self.session_factory() as session:
            try:
                session.add(
                    GoalModel(
                        indicador_id=goal.indicator_id,
                        periodo_id=goal.period_id,
                        valor=goal.value,
                    )
                )
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise ConflictError("Ya existe una meta para el indicador y periodo.") from exc

    async def get_goal(self, indicator_id: int, period_id: int) -> Goal | None:
        async with self.session_factory() as session:
            model = (
                await session.execute(
                    select(GoalModel).where(
                        GoalModel.indicador_id == indicator_id,
                        GoalModel.periodo_id == period_id,
                    )
                )
            ).scalar_one_or_none()
            if model is None:
                return None
            return Goal(
                indicator_id=model.indicador_id,
                period_id=model.periodo_id,
                value=model.valor,
            )

    async def get_baseline(self, indicator_id: int) -> Baseline | None:
        async with self.session_factory() as session:
            model = (
                await session.execute(
                    select(BaselineModel).where(BaselineModel.indicador_id == indicator_id)
                )
            ).scalar_one_or_none()
            if model is None:
                return None
            return Baseline(
                indicator_id=model.indicador_id,
                year=model.anio,
                period=model.periodo,
                value=model.valor,
            )

    async def list_goals(self, indicator_id: int) -> list[Goal]:
        async with self.session_factory() as session:
            models = (
                await session.scalars(
                    select(GoalModel)
                    .where(GoalModel.indicador_id == indicator_id)
                    .order_by(GoalModel.periodo_id)
                )
            ).all()
            return [
                Goal(indicator_id=model.indicador_id, period_id=model.periodo_id, value=model.valor)
                for model in models
            ]

    async def set_criteria(self, indicator_id: int, criteria_ids: set[int]) -> None:
        from sqlalchemy import delete

        async with self.session_factory() as session:
            await session.execute(
                delete(IndicatorCriteriaModel).where(
                    IndicatorCriteriaModel.c.indicador_id == indicator_id
                )
            )
            if criteria_ids:
                await session.execute(
                    insert(IndicatorCriteriaModel),
                    [
                        {"indicador_id": indicator_id, "criterio_seaes_id": criterion_id}
                        for criterion_id in sorted(criteria_ids)
                    ],
                )
            await session.commit()
