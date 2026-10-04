"""Adaptador PostgreSQL del catalogo de unidades de medida."""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.domain.exceptions import ConflictError

from ..domain.unit_of_measure_entities import UnitOfMeasure
from .models import UnitOfMeasureModel


def _to_domain(model: UnitOfMeasureModel) -> UnitOfMeasure:
    return UnitOfMeasure(
        id=model.id,
        key=model.clave,
        name=model.nombre,
        plural=model.plural,
        is_active=model.activo,
        version=model.version,
    )


class SqlAlchemyUnitOfMeasureRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def add(self, item: UnitOfMeasure) -> None:
        async with self.session_factory() as session:
            try:
                model = UnitOfMeasureModel(
                    clave=item.key,
                    nombre=item.name,
                    plural=item.plural,
                    activo=item.is_active,
                    version=item.version,
                )
                session.add(model)
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise ConflictError("La clave de la unidad de medida ya existe.") from exc
        item.id = model.id

    async def get_by_id(self, item_id: int) -> UnitOfMeasure | None:
        async with self.session_factory() as session:
            model = await session.get(UnitOfMeasureModel, item_id)
            return _to_domain(model) if model is not None else None

    async def list(self, *, active_only: bool = True) -> list[UnitOfMeasure]:
        async with self.session_factory() as session:
            statement = select(UnitOfMeasureModel).order_by(UnitOfMeasureModel.id)
            if active_only:
                statement = statement.where(UnitOfMeasureModel.activo.is_(True))
            models = (await session.scalars(statement)).all()
            return [_to_domain(model) for model in models]

    async def update(self, item: UnitOfMeasure) -> None:
        async with self.session_factory() as session:
            result = await session.execute(
                update(UnitOfMeasureModel)
                .where(
                    UnitOfMeasureModel.id == item.id,
                    UnitOfMeasureModel.version == item.version,
                )
                .values(
                    clave=item.key,
                    nombre=item.name,
                    plural=item.plural,
                    activo=item.is_active,
                    version=item.version + 1,
                )
            )
            if result.rowcount != 1:
                current = await session.scalar(
                    select(UnitOfMeasureModel.version).where(UnitOfMeasureModel.id == item.id)
                )
                raise ConflictError(
                    "La unidad de medida fue modificada por otra solicitud.",
                    details={"version_actual": current},
                )
            await session.commit()
            item.version += 1
