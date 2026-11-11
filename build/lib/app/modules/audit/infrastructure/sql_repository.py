"""Adaptador de solo escritura/lectura para la bitacora PostgreSQL."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.infrastructure.db.unit_of_work import commit_or_flush, session_scope

from ..domain.entities import AuditEntry
from .models import AuditModel


class SqlAlchemyAuditRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def append(self, entry: AuditEntry) -> None:
        async with session_scope(self.session_factory) as session:
            model = AuditModel(
                usuario_id=entry.actor_id,
                usuario_nombre=entry.actor_name,
                evento=entry.event_name,
                accion=entry.action or entry.event_name,
                entidad=entry.aggregate_type,
                entidad_id=entry.aggregate_id,
                valor_nuevo=entry.data,
                fecha=entry.occurred_at or datetime.now(UTC),
            )
            session.add(model)
            await commit_or_flush(session)

    async def list(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        actor_id: int | None = None,
        action: str | None = None,
        from_date=None,
        to_date=None,
        aggregate_type: str | None = None,
        aggregate_id: int | None = None,
        descending: bool = True,
    ) -> list[AuditEntry]:
        async with session_scope(self.session_factory) as session:
            statement = select(AuditModel)
            if actor_id is not None:
                statement = statement.where(AuditModel.usuario_id == actor_id)
            if action is not None:
                statement = statement.where(AuditModel.accion == action)
            if from_date is not None:
                statement = statement.where(AuditModel.fecha >= from_date)
            if to_date is not None:
                statement = statement.where(AuditModel.fecha <= to_date)
            if aggregate_type is not None:
                statement = statement.where(AuditModel.entidad == aggregate_type)
            if aggregate_id is not None:
                statement = statement.where(AuditModel.entidad_id == aggregate_id)
            date_order = AuditModel.fecha.desc() if descending else AuditModel.fecha.asc()
            id_order = AuditModel.id.desc() if descending else AuditModel.id.asc()
            models = (
                await session.scalars(
                    statement.order_by(date_order, id_order)
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
            return [
                AuditEntry(
                    id=model.id,
                    event_name=model.evento or model.accion,
                    occurred_at=model.fecha,
                    actor_id=model.usuario_id,
                    actor_name=model.usuario_nombre,
                    aggregate_type=model.entidad,
                    aggregate_id=model.entidad_id,
                    action=model.accion,
                    data=model.valor_nuevo or {},
                )
                for model in models
            ]

    async def count(
        self,
        *,
        actor_id: int | None = None,
        action: str | None = None,
        from_date=None,
        to_date=None,
        aggregate_type: str | None = None,
        aggregate_id: int | None = None,
        descending: bool = True,
    ) -> int:
        del descending
        async with session_scope(self.session_factory) as session:
            statement = select(func.count()).select_from(AuditModel)
            if actor_id is not None:
                statement = statement.where(AuditModel.usuario_id == actor_id)
            if action is not None:
                statement = statement.where(AuditModel.accion == action)
            if from_date is not None:
                statement = statement.where(AuditModel.fecha >= from_date)
            if to_date is not None:
                statement = statement.where(AuditModel.fecha <= to_date)
            if aggregate_type is not None:
                statement = statement.where(AuditModel.entidad == aggregate_type)
            if aggregate_id is not None:
                statement = statement.where(AuditModel.entidad_id == aggregate_id)
            return int((await session.execute(statement)).scalar_one())
