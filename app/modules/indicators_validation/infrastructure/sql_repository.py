"""Adaptador PostgreSQL del historial de capturas."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.infrastructure.db.unit_of_work import commit_or_flush, session_scope

from ...indicators_capture.domain.value_objects import CaptureStatus
from ..domain.entities import StateChange
from .models import StateChangeModel


class SqlAlchemyStateChangeRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def add(self, change: StateChange) -> None:
        async with session_scope(self.session_factory) as session:
            session.add(
                StateChangeModel(
                    entidad=change.entity,
                    entidad_id=change.entity_id,
                    de_estado=change.from_status.value if change.from_status else None,
                    a_estado=change.to_status.value,
                    usuario_id=change.user_id,
                    fecha=change.created_at,
                    comentario=change.comment,
                )
            )
            await commit_or_flush(session)

    async def list_for_capture(self, capture_id: int) -> list[StateChange]:
        async with session_scope(self.session_factory) as session:
            models = (
                await session.scalars(
                    select(StateChangeModel)
                    .where(
                        StateChangeModel.entidad == "captura",
                        StateChangeModel.entidad_id == capture_id,
                    )
                    .order_by(StateChangeModel.fecha, StateChangeModel.id)
                )
            ).all()
            return [
                StateChange(
                    id=model.id,
                    entity_id=model.entidad_id,
                    from_status=CaptureStatus(model.de_estado) if model.de_estado else None,
                    to_status=CaptureStatus(model.a_estado),
                    user_id=model.usuario_id,
                    comment=model.comentario,
                    created_at=model.fecha,
                )
                for model in models
            ]

    async def list_for_capture_page(
        self,
        capture_id: int,
        *,
        offset: int,
        limit: int,
        descending: bool,
        entity: str = "captura",
    ) -> tuple[list[StateChange], int]:
        # `cambios_estado` ya admite la entidad `poa_cedula_seguimiento` desde la
        # migracion 0023; la lectura estaba fijada a capturas sin necesidad.
        filters = (
            StateChangeModel.entidad == entity,
            StateChangeModel.entidad_id == capture_id,
        )
        async with session_scope(self.session_factory) as session:
            total = int(
                await session.scalar(
                    select(func.count()).select_from(StateChangeModel).where(*filters)
                )
                or 0
            )
            date_order = (
                StateChangeModel.fecha.desc()
                if descending
                else StateChangeModel.fecha.asc()
            )
            id_order = (
                StateChangeModel.id.desc() if descending else StateChangeModel.id.asc()
            )
            models = (
                await session.scalars(
                    select(StateChangeModel)
                    .where(*filters)
                    .order_by(date_order, id_order)
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
            return (
                [
                    StateChange(
                        id=model.id,
                        entity=model.entidad,
                        entity_id=model.entidad_id,
                        from_status=(
                            CaptureStatus(model.de_estado) if model.de_estado else None
                        ),
                        to_status=CaptureStatus(model.a_estado),
                        user_id=model.usuario_id,
                        comment=model.comentario,
                        created_at=model.fecha,
                    )
                    for model in models
                ],
                total,
            )
