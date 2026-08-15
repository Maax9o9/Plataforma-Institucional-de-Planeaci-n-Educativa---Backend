"""Adaptador PostgreSQL de evidencias."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.domain.exceptions import ConflictError

from ..domain.entities import Evidence, EvidenceLink, EvidenceVersion
from ..domain.value_objects import EvidenceType, FlowEntity
from .models import EvidenceLinkModel, EvidenceModel, EvidenceVersionModel


class SqlAlchemyEvidenceRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def add(self, evidence: Evidence) -> None:
        async with self.session_factory() as session:
            model = EvidenceModel(
                nombre=evidence.name,
                descripcion=evidence.description,
                fecha=evidence.evidence_date,
                tipo=evidence.evidence_type.value,
                subida_por=evidence.uploaded_by,
                creado_en=datetime.now(UTC),
            )
            session.add(model)
            await session.commit()
        evidence.id = model.id

    async def add_version(self, version: EvidenceVersion) -> None:
        async with self.session_factory() as session:
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
            await session.commit()

    async def link(self, link: EvidenceLink) -> None:
        async with self.session_factory() as session:
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
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise ConflictError("La evidencia ya esta vinculada a ese registro.") from exc

    async def has_for(self, entity: FlowEntity, entity_id: int) -> bool:
        async with self.session_factory() as session:
            result = await session.execute(
                select(EvidenceLinkModel.id).where(
                    EvidenceLinkModel.entidad == entity.value,
                    EvidenceLinkModel.entidad_id == entity_id,
                )
            )
            return result.scalar_one_or_none() is not None

    async def get(self, evidence_id: int) -> Evidence | None:
        async with self.session_factory() as session:
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
        async with self.session_factory() as session:
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
