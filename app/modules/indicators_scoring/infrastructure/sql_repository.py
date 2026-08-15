"""Adaptador PostgreSQL de configuracion de semaforos."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ...institutional_catalogs.infrastructure.models import SystemConfigModel
from ..domain.strategies import Thresholds


class SqlAlchemyThresholdConfigRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def get(self) -> Thresholds:
        async with self.session_factory() as session:
            model = await session.get(SystemConfigModel, 1)
            if model is None:
                return Thresholds(green=90, yellow=40)
            return Thresholds(green=model.umbral_verde_min, yellow=model.umbral_amarillo_min)

    async def update(self, thresholds: Thresholds, actor_id: int) -> None:
        async with self.session_factory() as session:
            model = await session.get(SystemConfigModel, 1)
            if model is None:
                model = SystemConfigModel(
                    id=1,
                    umbral_verde_min=thresholds.green,
                    umbral_amarillo_min=thresholds.yellow,
                    actualizado_en=datetime.now(UTC),
                    actualizado_por=actor_id,
                )
                session.add(model)
            else:
                model.umbral_verde_min = thresholds.green
                model.umbral_amarillo_min = thresholds.yellow
                model.actualizado_en = datetime.now(UTC)
                model.actualizado_por = actor_id
            await session.commit()
