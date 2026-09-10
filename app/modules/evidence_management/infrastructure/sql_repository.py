"""Adaptador PostgreSQL de evidencias."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.domain.exceptions import ConflictError
from app.shared.infrastructure.db.unit_of_work import commit_or_flush, session_scope

from ..domain.entities import Evidence, EvidenceLink, EvidenceVersion
from ..domain.value_objects import EvidenceType, FlowEntity
from .models import EvidenceLinkModel, EvidenceModel, EvidenceVersionModel


class SqlAlchemyEvidenceRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def add(self, evidence: Evidence) -> None:
        async with session_scope(self.session_factory) as session:
            model = EvidenceModel(
                nombre=evidence.name,
                descripcion=evidence.description,
                fecha=evidence.evidence_date,
                tipo=evidence.evidence_type.value,
                subida_por=evidence.uploaded_by,
                creado_en=datetime.now(UTC),
            )
            session.add(model)
            await commit_or_flush(session)
        evidence.id = model.id

    async def add_version(self, version: EvidenceVersion) -> None:
        async with session_scope(self.session_factory) as session:
            session.add(
                EvidenceVersionModel(
                    evidencia_id=version.evidence_id,
                    ruta_o_url=version.path_or_url,
                    mime_type=version.mime_type,
                    tamanio_bytes=version.size_bytes,
                    checksum_sha256=version.checksum_sha256,
                    usuario_id=version.user_id,
                    fecha=version.created_at,
                )
            )
            await commit_or_flush(session)

    async def link(self, link: EvidenceLink) -> None:
        async with session_scope(self.session_factory) as session:
            try:
                session.add(
                    EvidenceLinkModel(
                        evidencia_id=link.evidence_id,
                        entidad=link.entity.value,
                        entidad_id=link.entity_id,
                        vinculado_por=link.linked_by,
                        fecha=datetime.now(UTC),
                    )
                )
                await commit_or_flush(session)
            except IntegrityError as exc:
                await session.rollback()
                raise ConflictError("La evidencia ya esta vinculada a ese registro.") from exc

    async def has_for(self, entity: FlowEntity, entity_id: int) -> bool:
        async with session_scope(self.session_factory) as session:
            result = await session.execute(
                select(EvidenceLinkModel.id).where(
                    EvidenceLinkModel.entidad == entity.value,
                    EvidenceLinkModel.entidad_id == entity_id,
                ).limit(1)
            )
            return result.scalar_one_or_none() is not None

    async def count_by_entity(
        self, entity: FlowEntity, entity_ids: list[int]
    ) -> dict[int, int]:
        if not entity_ids:
            return {}
        async with session_scope(self.session_factory) as session:
            rows = await session.execute(
                select(EvidenceLinkModel.entidad_id, func.count())
                .where(
                    EvidenceLinkModel.entidad == entity.value,
                    EvidenceLinkModel.entidad_id.in_(entity_ids),
                )
                .group_by(EvidenceLinkModel.entidad_id)
            )
            return {entity_id: total for entity_id, total in rows.all()}

    async def get(self, evidence_id: int) -> Evidence | None:
        async with session_scope(self.session_factory) as session:
            model = await session.get(EvidenceModel, evidence_id)
            if model is None:
                return None
            return Evidence(
                id=model.id,
                name=model.nombre,
                description=model.descripcion,
                evidence_date=model.fecha,
                evidence_type=EvidenceType(model.tipo),
                uploaded_by=model.subida_por,
            )

    async def list_all(self) -> list[Evidence]:
        async with session_scope(self.session_factory) as session:
            models = (await session.scalars(select(EvidenceModel).order_by(EvidenceModel.id))).all()
            return [
                Evidence(
                    id=model.id,
                    name=model.nombre,
                    description=model.descripcion,
                    evidence_date=model.fecha,
                    evidence_type=EvidenceType(model.tipo),
                    uploaded_by=model.subida_por,
                )
                for model in models
            ]

    async def list_for(self, entity: FlowEntity, entity_id: int) -> list[Evidence]:
        async with session_scope(self.session_factory) as session:
            models = (
                await session.scalars(
                    select(EvidenceModel)
                    .join(EvidenceLinkModel, EvidenceLinkModel.evidencia_id == EvidenceModel.id)
                    .where(
                        EvidenceLinkModel.entidad == entity.value,
                        EvidenceLinkModel.entidad_id == entity_id,
                    )
                    .order_by(EvidenceModel.id)
                )
            ).all()
            return [
                Evidence(
                    id=model.id,
                    name=model.nombre,
                    description=model.descripcion,
                    evidence_date=model.fecha,
                    evidence_type=EvidenceType(model.tipo),
                    uploaded_by=model.subida_por,
                )
                for model in models
            ]

    async def list_versions(self, evidence_id: int) -> list[EvidenceVersion]:
        async with session_scope(self.session_factory) as session:
            models = (
                await session.scalars(
                    select(EvidenceVersionModel)
                    .where(EvidenceVersionModel.evidencia_id == evidence_id)
                    .order_by(EvidenceVersionModel.fecha, EvidenceVersionModel.id)
                )
            ).all()
            return [
                EvidenceVersion(
                    evidence_id=model.evidencia_id,
                    path_or_url=model.ruta_o_url,
                    mime_type=model.mime_type,
                    size_bytes=model.tamanio_bytes,
                    checksum_sha256=model.checksum_sha256,
                    user_id=model.usuario_id,
                    created_at=model.fecha,
                )
                for model in models
            ]

    async def list_versions_page(
        self,
        evidence_id: int,
        *,
        offset: int,
        limit: int,
        descending: bool,
    ) -> tuple[list[tuple[int, EvidenceVersion]], int]:
        async with session_scope(self.session_factory) as session:
            total = int(
                await session.scalar(
                    select(func.count())
                    .select_from(EvidenceVersionModel)
                    .where(EvidenceVersionModel.evidencia_id == evidence_id)
                )
                or 0
            )
            date_order = (
                EvidenceVersionModel.fecha.desc()
                if descending
                else EvidenceVersionModel.fecha.asc()
            )
            id_order = (
                EvidenceVersionModel.id.desc()
                if descending
                else EvidenceVersionModel.id.asc()
            )
            models = (
                await session.scalars(
                    select(EvidenceVersionModel)
                    .where(EvidenceVersionModel.evidencia_id == evidence_id)
                    .order_by(date_order, id_order)
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
            numbers = (
                range(total - offset, total - offset - len(models), -1)
                if descending
                else range(offset + 1, offset + 1 + len(models))
            )
            return [
                (
                    number,
                    EvidenceVersion(
                        evidence_id=model.evidencia_id,
                        path_or_url=model.ruta_o_url,
                        mime_type=model.mime_type,
                        size_bytes=model.tamanio_bytes,
                        checksum_sha256=model.checksum_sha256,
                        user_id=model.usuario_id,
                        created_at=model.fecha,
                    ),
                )
                for number, model in zip(numbers, models, strict=True)
            ], total

    async def list_links(self, evidence_id: int) -> list[EvidenceLink]:
        async with session_scope(self.session_factory) as session:
            models = (
                await session.scalars(
                    select(EvidenceLinkModel)
                    .where(EvidenceLinkModel.evidencia_id == evidence_id)
                    .order_by(EvidenceLinkModel.id)
                )
            ).all()
            return [
                EvidenceLink(
                    evidence_id=model.evidencia_id,
                    entity=FlowEntity(model.entidad),
                    entity_id=model.entidad_id,
                    linked_by=model.vinculado_por,
                )
                for model in models
            ]

    async def find_evidence_id_by_path(self, path: str) -> int | None:
        async with session_scope(self.session_factory) as session:
            return await session.scalar(
                select(EvidenceVersionModel.evidencia_id)
                .where(EvidenceVersionModel.ruta_o_url == path)
                .order_by(EvidenceVersionModel.id.desc())
                .limit(1)
            )

    async def unlink(self, evidence_id: int, entity: FlowEntity, entity_id: int) -> bool:
        async with session_scope(self.session_factory) as session:
            result = await session.execute(
                delete(EvidenceLinkModel).where(
                    EvidenceLinkModel.evidencia_id == evidence_id,
                    EvidenceLinkModel.entidad == entity.value,
                    EvidenceLinkModel.entidad_id == entity_id,
                )
            )
            await commit_or_flush(session)
            return bool(result.rowcount)
