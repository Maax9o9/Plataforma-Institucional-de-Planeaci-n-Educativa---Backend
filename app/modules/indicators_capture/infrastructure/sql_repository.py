"""Adaptador PostgreSQL del dueño de capturas."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.domain.exceptions import ConflictError
from app.shared.infrastructure.db.unit_of_work import commit_or_flush, session_scope

from ..domain.entities import Capture
from ..domain.value_objects import CaptureStatus
from .models import CaptureModel


class SqlAlchemyCaptureRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    @staticmethod
    def _to_domain(model: CaptureModel) -> Capture:
        return Capture(
            id=model.id,
            indicator_id=model.indicador_id,
            period_id=model.periodo_id,
            capturer_id=model.capturista_id,
            result=model.resultado,
            source_data=model.datos_fuente,
            activity=model.actividad_realizada,
            observations=model.observaciones,
            status=CaptureStatus(model.estado),
            progress_percentage=model.pct_avance,
            semaphore=model.semaforo,
            created_at=model.creado_en,
            updated_at=model.actualizado_en,
        )

    async def add(self, capture: Capture) -> None:
        now = datetime.now(UTC)
        async with session_scope(self.session_factory) as session:
            try:
                model = CaptureModel(
                    indicador_id=capture.indicator_id,
                    periodo_id=capture.period_id,
                    capturista_id=capture.capturer_id,
                    resultado=capture.result,
                    datos_fuente=capture.source_data,
                    actividad_realizada=capture.activity,
                    observaciones=capture.observations,
                    estado=capture.status.value,
                    creado_en=now,
                    actualizado_en=now,
                )
                session.add(model)
                await commit_or_flush(session)
            except IntegrityError as exc:
                await session.rollback()
                raise ConflictError("Ya existe una captura para el indicador y periodo.") from exc
        capture.id = model.id
        capture.created_at = now
        capture.updated_at = now

    async def get_by_id(self, capture_id: int) -> Capture | None:
        async with session_scope(self.session_factory) as session:
            model = await session.get(CaptureModel, capture_id)
            return self._to_domain(model) if model else None

    async def get_by_indicator_period(self, indicator_id: int, period_id: int) -> Capture | None:
        async with session_scope(self.session_factory) as session:
            model = (
                await session.execute(
                    select(CaptureModel).where(
                        CaptureModel.indicador_id == indicator_id,
                        CaptureModel.periodo_id == period_id,
                    )
                )
            ).scalar_one_or_none()
            return self._to_domain(model) if model else None

    async def update(self, capture: Capture) -> None:
        async with session_scope(self.session_factory) as session:
            model = await session.get(CaptureModel, capture.id)
            if model is None:
                return
            model.resultado = capture.result
            model.datos_fuente = capture.source_data
            model.actividad_realizada = capture.activity
            model.observaciones = capture.observations
            model.estado = capture.status.value
            model.actualizado_en = capture.updated_at
            await commit_or_flush(session)

    async def list_by_capturer(
        self,
        capturer_id: int,
        period_id: int | None = None,
    ) -> list[Capture]:
        async with session_scope(self.session_factory) as session:
            statement = select(CaptureModel).where(CaptureModel.capturista_id == capturer_id)
            if period_id is not None:
                statement = statement.where(CaptureModel.periodo_id == period_id)
            models = (await session.scalars(statement.order_by(CaptureModel.id))).all()
            return [self._to_domain(model) for model in models]

    async def list_by_indicator(self, indicator_id: int) -> list[Capture]:
        async with session_scope(self.session_factory) as session:
            models = (
                await session.scalars(
                    select(CaptureModel)
                    .where(
                        CaptureModel.indicador_id == indicator_id,
                        CaptureModel.estado == "validado",
                    )
                    .order_by(CaptureModel.periodo_id)
                )
            ).all()
            return [self._to_domain(model) for model in models]

    async def update_evaluation(self, capture_id: int, progress_percentage, semaphore: str) -> None:
        async with session_scope(self.session_factory) as session:
            model = await session.get(CaptureModel, capture_id)
            if model is None:
                return
            model.pct_avance = progress_percentage
            model.semaforo = semaphore
            model.actualizado_en = datetime.now(UTC)
            await commit_or_flush(session)

    async def list_all(self) -> list[Capture]:
        async with session_scope(self.session_factory) as session:
            models = (await session.scalars(select(CaptureModel).order_by(CaptureModel.id))).all()
            return [self._to_domain(model) for model in models]

    async def reset_validated_for_period(self, period_id: int, actor_id: int) -> list[int]:
        del actor_id
        reset_ids = []
        async with session_scope(self.session_factory) as session:
            models = await session.scalars(
                select(CaptureModel).where(
                    CaptureModel.periodo_id == period_id,
                    CaptureModel.estado == "validado",
                )
            )
            for model in models:
                reset_ids.append(model.id)
                model.estado = "borrador"
                model.pct_avance = None
                model.semaforo = None
                model.actualizado_en = datetime.now(UTC)
            await commit_or_flush(session)
        return reset_ids
