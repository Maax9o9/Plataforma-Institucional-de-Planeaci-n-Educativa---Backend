"""Adaptador PostgreSQL de periods."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.domain.exceptions import ConflictError
from app.shared.infrastructure.db.unit_of_work import commit_or_flush, session_scope

from ..domain.entities import Period
from ..domain.value_objects import Periodicity, PeriodStatus, PeriodType
from .models import PeriodModel


class SqlAlchemyPeriodRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    @staticmethod
    def _to_domain(model: PeriodModel) -> Period:
        return Period(
            id=model.id,
            name=model.etiqueta,
            starts_on=model.fecha_inicio,
            ends_on=model.fecha_limite,
            period_type=PeriodType(model.tipo),
            periodicity=Periodicity(model.periodicidad) if model.periodicidad else None,
            year=model.anio,
            status=PeriodStatus(model.estado),
            reopen_reason=model.motivo_reapertura,
            reopened_by=model.reabierto_por,
        )

    async def add(self, period: Period) -> None:
        async with session_scope(self.session_factory) as session:
            try:
                model = PeriodModel(
                    tipo=period.period_type.value,
                    periodicidad=period.periodicity.value if period.periodicity else None,
                    anio=period.year,
                    etiqueta=period.name,
                    fecha_inicio=period.starts_on,
                    fecha_limite=period.ends_on,
                    estado=period.status.value,
                )
                async with session.begin_nested():
                    session.add(model)
                    await session.flush()
                await commit_or_flush(session)
            except IntegrityError as exc:
                raise ConflictError("El periodo ya existe o sus datos no son validos.") from exc
        period.id = model.id

    async def get_by_id(self, period_id: int) -> Period | None:
        async with session_scope(self.session_factory) as session:
            model = await session.get(PeriodModel, period_id)
            return self._to_domain(model) if model else None

    async def list(self) -> list[Period]:
        async with session_scope(self.session_factory) as session:
            models = (
                await session.scalars(
                    select(PeriodModel).order_by(PeriodModel.fecha_inicio, PeriodModel.id)
                )
            ).all()
            return [self._to_domain(model) for model in models]

    async def update(self, period: Period) -> None:
        async with session_scope(self.session_factory) as session:
            model = await session.get(PeriodModel, period.id)
            if model is None:
                return
            model.estado = period.status.value
            if period.reopen_reason:
                model.motivo_reapertura = period.reopen_reason
                model.reabierto_por = period.reopened_by
                model.reabierto_en = datetime.now(UTC)
            await commit_or_flush(session)
