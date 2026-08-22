"""Adaptador PostgreSQL de avances POA."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.domain.exceptions import ConflictError
from app.shared.infrastructure.db.unit_of_work import commit_or_flush, session_scope

from ...indicators_capture.domain.value_objects import CaptureStatus
from ..domain.entities import PoaAdvance
from .models import PoaAdvanceCriteriaModel, PoaAdvanceModel


class SqlAlchemyPoaAdvanceRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def _to_domain(self, session: AsyncSession, model: PoaAdvanceModel) -> PoaAdvance:
        criteria = await session.execute(
            select(PoaAdvanceCriteriaModel.c.criterio_seaes_id).where(
                PoaAdvanceCriteriaModel.c.poa_avance_id == model.id
            )
        )
        return PoaAdvance(
            id=model.id,
            activity_id=model.actividad_id,
            quarter=model.cuatrimestre,
            period_id=model.periodo_id,
            capturer_id=model.capturista_id,
            scheduled=model.programado,
            achieved=model.alcanzado,
            observations=model.observaciones,
            compliance_percentage=model.pct_cumplimiento,
            status=CaptureStatus(model.estado),
            criteria_ids=set(criteria.scalars().all()),
            created_at=model.creado_en,
            updated_at=model.actualizado_en,
        )

    async def add(self, item: PoaAdvance) -> None:
        now = datetime.now(UTC)
        async with session_scope(self.session_factory) as session:
            try:
                model = PoaAdvanceModel(
                    actividad_id=item.activity_id,
                    cuatrimestre=item.quarter,
                    periodo_id=item.period_id,
                    capturista_id=item.capturer_id,
                    programado=item.scheduled,
                    alcanzado=item.achieved,
                    observaciones=item.observations,
                    pct_cumplimiento=item.compliance_percentage,
                    estado=item.status.value,
                    creado_en=now,
                    actualizado_en=now,
                )
                session.add(model)
                await session.flush()
                if item.criteria_ids:
                    await session.execute(
                        insert(PoaAdvanceCriteriaModel),
                        [
                            {"poa_avance_id": model.id, "criterio_seaes_id": criterion_id}
                            for criterion_id in item.criteria_ids
                        ],
                    )
                await commit_or_flush(session)
            except IntegrityError as exc:
                await session.rollback()
                raise ConflictError(
                    "Ya existe un avance para la actividad y cuatrimestre."
                ) from exc
        item.id = model.id
        item.created_at = now
        item.updated_at = now

    async def get_by_id(self, item_id: int) -> PoaAdvance | None:
        async with session_scope(self.session_factory) as session:
            model = await session.get(PoaAdvanceModel, item_id)
            return await self._to_domain(session, model) if model else None

    async def get_by_activity_quarter(self, activity_id: int, quarter: int) -> PoaAdvance | None:
        async with session_scope(self.session_factory) as session:
            model = (
                await session.execute(
                    select(PoaAdvanceModel).where(
                        PoaAdvanceModel.actividad_id == activity_id,
                        PoaAdvanceModel.cuatrimestre == quarter,
                    )
                )
            ).scalar_one_or_none()
            return await self._to_domain(session, model) if model else None

    async def update(self, item: PoaAdvance) -> None:
        async with session_scope(self.session_factory) as session:
            model = await session.get(PoaAdvanceModel, item.id)
            if model is None:
                return
            model.programado = item.scheduled
            model.alcanzado = item.achieved
            model.observaciones = item.observations
            model.pct_cumplimiento = item.compliance_percentage
            model.estado = item.status.value
            model.actualizado_en = item.updated_at
            await session.execute(
                delete(PoaAdvanceCriteriaModel).where(
                    PoaAdvanceCriteriaModel.c.poa_avance_id == item.id
                )
            )
            if item.criteria_ids:
                await session.execute(
                    insert(PoaAdvanceCriteriaModel),
                    [
                        {"poa_avance_id": item.id, "criterio_seaes_id": criterion_id}
                        for criterion_id in item.criteria_ids
                    ],
                )
            await commit_or_flush(session)

    async def list_by_activity(self, activity_id: int) -> list[PoaAdvance]:
        async with session_scope(self.session_factory) as session:
            models = (
                await session.scalars(
                    select(PoaAdvanceModel)
                    .where(PoaAdvanceModel.actividad_id == activity_id)
                    .order_by(PoaAdvanceModel.cuatrimestre)
                )
            ).all()
            return [await self._to_domain(session, model) for model in models]

    async def list_by_capturer(self, capturer_id: int) -> list[PoaAdvance]:
        async with session_scope(self.session_factory) as session:
            models = (
                await session.scalars(
                    select(PoaAdvanceModel)
                    .where(PoaAdvanceModel.capturista_id == capturer_id)
                    .order_by(PoaAdvanceModel.id)
                )
            ).all()
            return [await self._to_domain(session, model) for model in models]

    async def has_validated_for_activity(self, activity_id: int) -> bool:
        async with session_scope(self.session_factory) as session:
            result = await session.execute(
                select(PoaAdvanceModel.id).where(
                    PoaAdvanceModel.actividad_id == activity_id,
                    PoaAdvanceModel.estado == "validado",
                )
            )
            return result.scalar_one_or_none() is not None

    async def reset_validated_for_period(self, period_id: int, actor_id: int) -> list[int]:
        reset_ids = []
        async with session_scope(self.session_factory) as session:
            models = await session.scalars(
                select(PoaAdvanceModel).where(
                    PoaAdvanceModel.periodo_id == period_id,
                    PoaAdvanceModel.estado == "validado",
                )
            )
            for model in models:
                reset_ids.append(model.id)
                model.estado = "borrador"
                model.actualizado_en = datetime.now(UTC)
            await commit_or_flush(session)
        return reset_ids
