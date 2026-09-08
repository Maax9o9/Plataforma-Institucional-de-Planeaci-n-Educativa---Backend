"""Adaptador PostgreSQL de notificaciones idempotentes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.infrastructure.db.unit_of_work import commit_or_flush, session_scope

from ..domain.entities import Notification
from .models import NotificationModel


class SqlAlchemyNotificationRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    @staticmethod
    def _to_domain(model: NotificationModel) -> Notification:
        return Notification(
            id=model.id,
            user_id=model.usuario_id,
            notification_type=model.tipo,
            message=model.mensaje,
            entity=model.entidad,
            entity_id=model.entidad_id,
            read=model.leida,
            sent_by_email=model.enviada_por_correo,
            source_event_id=model.origen_evento_id,
            created_at=model.fecha,
        )

    async def create(self, notification: Notification) -> Notification:
        async with session_scope(self.session_factory) as session:
            model = NotificationModel(
                usuario_id=notification.user_id,
                tipo=notification.notification_type,
                entidad=notification.entity,
                entidad_id=notification.entity_id,
                mensaje=notification.message,
                origen_evento_id=notification.source_event_id,
                fecha=notification.created_at or datetime.now(UTC),
            )
            try:
                async with session.begin_nested():
                    session.add(model)
                    await session.flush()
                await commit_or_flush(session)
            except IntegrityError:
                result = await session.execute(
                    select(NotificationModel).where(
                        NotificationModel.usuario_id == notification.user_id,
                        NotificationModel.tipo == notification.notification_type,
                        NotificationModel.origen_evento_id == notification.source_event_id,
                    )
                )
                existing = result.scalar_one()
                return self._to_domain(existing)
            notification.id = model.id
            return notification

    async def list_for_user(self, user_id: int, unread_only: bool = False) -> list[Notification]:
        async with session_scope(self.session_factory) as session:
            statement = select(NotificationModel).where(NotificationModel.usuario_id == user_id)
            if unread_only:
                statement = statement.where(NotificationModel.leida.is_(False))
            models = (
                await session.scalars(statement.order_by(NotificationModel.fecha.desc()))
            ).all()
            return [self._to_domain(model) for model in models]

    async def mark_read(self, notification_id: int, user_id: int) -> None:
        async with session_scope(self.session_factory) as session:
            model = await session.get(NotificationModel, notification_id)
            if model and model.usuario_id == user_id:
                model.leida = True
                await commit_or_flush(session)

    async def mark_email_sent(self, notification_id: int) -> None:
        async with session_scope(self.session_factory) as session:
            model = await session.get(NotificationModel, notification_id)
            if model:
                model.enviada_por_correo = True
                model.correo_reservado_hasta = None
                await commit_or_flush(session)

    @staticmethod
    def _unclaimed():
        return or_(
            NotificationModel.correo_reservado_hasta.is_(None),
            NotificationModel.correo_reservado_hasta <= datetime.now(UTC),
        )

    async def pending_email(self, limit: int = 100, after_id: int = 0) -> list[Notification]:
        async with session_scope(self.session_factory) as session:
            models = await session.scalars(
                select(NotificationModel)
                .where(NotificationModel.enviada_por_correo.is_(False), self._unclaimed())
                .where(NotificationModel.id > after_id)
                .order_by(NotificationModel.id)
                .limit(limit)
            )
            return [self._to_domain(model) for model in models]

    async def claim_email(self, notification_id: int) -> bool:
        async with session_scope(self.session_factory) as session:
            result = await session.execute(
                update(NotificationModel)
                .where(
                    NotificationModel.id == notification_id,
                    NotificationModel.enviada_por_correo.is_(False),
                    self._unclaimed(),
                )
                .values(correo_reservado_hasta=datetime.now(UTC) + timedelta(minutes=5))
            )
            await commit_or_flush(session)
            return result.rowcount == 1

    async def release_email(self, notification_id: int) -> None:
        async with session_scope(self.session_factory) as session:
            await session.execute(
                update(NotificationModel)
                .where(NotificationModel.id == notification_id)
                .values(correo_reservado_hasta=None)
            )
            await commit_or_flush(session)
