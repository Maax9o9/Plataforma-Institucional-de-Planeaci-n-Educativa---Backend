"""Adaptadores PostgreSQL de institutional_catalogs."""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.domain.exceptions import ConflictError, ValidationError
from app.shared.infrastructure.db.constraints import viola_la_restriccion

from ..domain.entities import Area, Instrument, InstrumentVersion
from .models import AreaModel, InstrumentModel, InstrumentVersionModel

_UNICA_ETIQUETA_DE_LA_VERSION = "uq_instrumento_version_etiqueta"
_FORANEA_DEL_INSTRUMENTO = "fk_instrumento_version_instrumento"


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
                    tipo=area.area_type,
                    color=area.color,
                    version=area.version,
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
                    area_type=model.tipo,
                    color=model.color,
                    is_active=model.activo,
                    version=model.version,
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
                area_type=model.tipo,
                color=model.color,
                is_active=model.activo,
                version=model.version,
            )

    async def update(self, area: Area) -> None:
        async with self.session_factory() as session:
            try:
                result = await session.execute(
                    update(AreaModel)
                    .where(AreaModel.id == area.id, AreaModel.version == area.version)
                    .values(
                        nombre=area.name,
                        codigo=area.code,
                        parent_id=area.parent_id,
                        tipo=area.area_type,
                        color=area.color,
                        activo=area.is_active,
                        version=area.version + 1,
                    )
                )
                if result.rowcount != 1:
                    current = await session.scalar(
                        select(AreaModel.version).where(AreaModel.id == area.id)
                    )
                    raise ConflictError(
                        "El area fue modificada por otra solicitud.",
                        details={"version_actual": current},
                    )
                await session.commit()
                area.version += 1
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
                    version=instrument.version,
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
                    version=model.version,
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
                version=model.version,
            )

    async def update(self, instrument: Instrument) -> None:
        async with self.session_factory() as session:
            try:
                result = await session.execute(
                    update(InstrumentModel)
                    .where(
                        InstrumentModel.id == instrument.id,
                        InstrumentModel.version == instrument.version,
                    )
                    .values(
                        nombre=instrument.name,
                        codigo=instrument.code,
                        descripcion=instrument.description,
                        activo=instrument.is_active,
                        version=instrument.version + 1,
                    )
                )
                if result.rowcount != 1:
                    current = await session.scalar(
                        select(InstrumentModel.version).where(
                            InstrumentModel.id == instrument.id
                        )
                    )
                    raise ConflictError(
                        "El instrumento fue modificado por otra solicitud.",
                        details={"version_actual": current},
                    )
                await session.commit()
                instrument.version += 1
            except IntegrityError as exc:
                await session.rollback()
                raise ConflictError("Ya existe un instrumento con ese codigo o nombre.") from exc


def _version_a_dominio(model: InstrumentVersionModel) -> InstrumentVersion:
    return InstrumentVersion(
        id=model.id,
        instrument_id=model.instrumento_id,
        label=model.etiqueta,
        effective_from=model.vigente_desde,
        published_at=model.publicada_en,
        origin=model.origen,
    )


class SqlAlchemyInstrumentVersionRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def add(self, version: InstrumentVersion) -> None:
        async with self.session_factory() as session:
            model = InstrumentVersionModel(
                instrumento_id=version.instrument_id,
                etiqueta=version.label,
                vigente_desde=version.effective_from,
                publicada_en=version.published_at,
                origen=version.origin,
            )
            session.add(model)
            try:
                await session.flush()
            except IntegrityError as exc:
                await session.rollback()
                if viola_la_restriccion(exc, _UNICA_ETIQUETA_DE_LA_VERSION):
                    raise ConflictError(
                        f"El instrumento ya tiene una version con la etiqueta «{version.label}»."
                    ) from exc
                if viola_la_restriccion(exc, _FORANEA_DEL_INSTRUMENTO):
                    raise ValidationError("El instrumento de la version no existe.") from exc
                raise
            nuevo_id = model.id
            await session.commit()
        version.id = nuevo_id

    async def get_by_label(self, instrument_id: int, label: str) -> InstrumentVersion | None:
        async with self.session_factory() as session:
            model = await session.scalar(
                select(InstrumentVersionModel).where(
                    InstrumentVersionModel.instrumento_id == instrument_id,
                    InstrumentVersionModel.etiqueta == label,
                )
            )
            return _version_a_dominio(model) if model is not None else None
