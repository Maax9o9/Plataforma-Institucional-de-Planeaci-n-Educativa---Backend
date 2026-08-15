"""Adaptador de solo escritura/lectura para la bitacora PostgreSQL."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..domain.entities import AuditEntry
from .models import AuditModel


class SqlAlchemyAuditRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def append(self, entry: AuditEntry) -> None:
        async with self.session_factory() as session:
            model = AuditModel(
                usuario_id=entry.actor_id,
                evento=entry.event_name,
                accion=entry.action or entry.event_name,
                entidad=entry.aggregate_type,
                entidad_id=entry.aggregate_id,
                valor_nuevo=entry.data,
                fecha=entry.occurred_at or datetime.now(UTC),
            )
            session.add(model)
            await session.commit()

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
    ) -> list[AuditEntry]:
        async with self.session_factory() as session:
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
            models = (
                await session.scalars(
                    statement.order_by(AuditModel.fecha, AuditModel.id)
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
                    aggregate_type=model.entidad,
                    aggregate_id=model.entidad_id,
                    action=model.accion,
                    data=model.valor_nuevo or {},
                )
                for model in models
            ]
