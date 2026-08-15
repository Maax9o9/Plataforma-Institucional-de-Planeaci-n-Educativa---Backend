"""Adaptadores SQLAlchemy de catalogos auxiliares."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.domain.exceptions import ConflictError

from ..domain.reference_entities import ReferenceItem


class SqlAlchemyReferenceRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], model) -> None:
        self.session_factory = session_factory
        self.model = model
        self.is_criteria = hasattr(model, "clave")

    async def add(self, item: ReferenceItem) -> None:
        async with self.session_factory() as session:
            try:
                if self.is_criteria:
                    model = self.model(
                        clave=item.key,
                        nombre=item.name,
                        activo=item.is_active,
                    )
                else:
                    model = self.model(nombre=item.name, activo=item.is_active)
                session.add(model)
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise ConflictError("La clave o nombre del catalogo ya existe.") from exc
        item.id = model.id

    async def get_by_id(self, item_id: int) -> ReferenceItem | None:
        async with self.session_factory() as session:
            model = await session.get(self.model, item_id)
            if model is None:
                return None
            return ReferenceItem(
                id=model.id,
                key=model.clave if self.is_criteria else model.nombre,
                name=model.nombre,
                is_active=model.activo,
            )

    async def list(self, *, active_only: bool = True) -> list[ReferenceItem]:
        async with self.session_factory() as session:
            statement = select(self.model).order_by(self.model.id)
            if active_only:
                statement = statement.where(self.model.activo.is_(True))
            models = (await session.scalars(statement)).all()
            return [
                ReferenceItem(
                    id=model.id,
                key=model.clave if self.is_criteria else model.nombre,
                    name=model.nombre,
                    is_active=model.activo,
                )
                for model in models
            ]

    async def update(self, item: ReferenceItem) -> None:
        async with self.session_factory() as session:
            model = await session.get(self.model, item.id)
            if model is None:
                return
            model.nombre = item.name
            model.activo = item.is_active
            if self.is_criteria:
                model.clave = item.key
            await session.commit()
