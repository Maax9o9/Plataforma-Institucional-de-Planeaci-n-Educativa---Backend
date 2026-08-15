"""Adaptadores PostgreSQL de institutional_catalogs."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.domain.exceptions import ConflictError

from ..domain.entities import Area, Instrument
from .models import AreaModel, InstrumentModel


class SqlAlchemyAreaRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def add(self, area: Area) -> None:
        async with self.session_factory() as session:
            try:
                model = AreaModel(
                    nombre=area.name,
                    activo=area.is_active,
                    codigo=area.code,
                    parent_id=area.parent_id,
                )
                session.add(model)
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise ConflictError("Ya existe un area con ese codigo o nombre.") from exc
        area.id = model.id

    async def list(self, *, active_only: bool = True) -> list[Area]:
        async with self.session_factory() as session:
            statement = select(AreaModel).order_by(AreaModel.nombre)
            if active_only:
                statement = statement.where(AreaModel.activo.is_(True))
            models = (await session.scalars(statement)).all()
            return [
                Area(
                    id=model.id,
                    code=model.codigo or model.nombre,
                    name=model.nombre,
                    parent_id=model.parent_id,
                    is_active=model.activo,
                )
                for model in models
            ]

    async def get_by_id(self, area_id: int) -> Area | None:
        async with self.session_factory() as session:
            model = await session.get(AreaModel, area_id)
            if model is None:
                return None
            return Area(
                id=model.id,
                code=model.codigo or model.nombre,
                name=model.nombre,
                parent_id=model.parent_id,
                is_active=model.activo,
            )

    async def update(self, area: Area) -> None:
        async with self.session_factory() as session:
            try:
                model = await session.get(AreaModel, area.id)
                if model is None:
                    return
                model.nombre = area.name
                model.codigo = area.code
                model.parent_id = area.parent_id
                model.activo = area.is_active
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise ConflictError("Ya existe un area con ese codigo o nombre.") from exc


class SqlAlchemyInstrumentRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def add(self, instrument: Instrument) -> None:
        async with self.session_factory() as session:
            try:
                model = InstrumentModel(
                    nombre=instrument.name,
                    activo=instrument.is_active,
                    codigo=instrument.code,
                    descripcion=instrument.description,
                )
                session.add(model)
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise ConflictError("Ya existe un instrumento con ese nombre.") from exc
        instrument.id = model.id

    async def list(self, *, active_only: bool = True) -> list[Instrument]:
        async with self.session_factory() as session:
            statement = select(InstrumentModel).order_by(InstrumentModel.nombre)
            if active_only:
                statement = statement.where(InstrumentModel.activo.is_(True))
            models = (await session.scalars(statement)).all()
            return [
                Instrument(
                    id=model.id,
                    code=model.codigo or model.nombre,
                    name=model.nombre,
                    description=model.descripcion,
                    is_active=model.activo,
                )
                for model in models
            ]

    async def get_by_id(self, instrument_id: int) -> Instrument | None:
        async with self.session_factory() as session:
            model = await session.get(InstrumentModel, instrument_id)
            if model is None:
                return None
            return Instrument(
                id=model.id,
                code=model.codigo or model.nombre,
                name=model.nombre,
                description=model.descripcion,
                is_active=model.activo,
            )

    async def update(self, instrument: Instrument) -> None:
        async with self.session_factory() as session:
            try:
                model = await session.get(InstrumentModel, instrument.id)
                if model is None:
                    return
                model.nombre = instrument.name
                model.codigo = instrument.code
                model.descripcion = instrument.description
                model.activo = instrument.is_active
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise ConflictError("Ya existe un instrumento con ese codigo o nombre.") from exc
