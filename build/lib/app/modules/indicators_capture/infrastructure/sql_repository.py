"""Adaptador PostgreSQL del dueño de capturas."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.evidence_management.infrastructure.models import EvidenceLinkModel
from app.modules.identity_access.infrastructure.models import UserModel
from app.modules.indicators_catalog.infrastructure.models import GoalModel, IndicatorModel
from app.modules.institutional_catalogs.infrastructure.models import AreaModel
from app.modules.periods.infrastructure.models import PeriodModel
from app.shared.domain.exceptions import ConflictError
from app.shared.infrastructure.db.unit_of_work import commit_or_flush, session_scope

from ..application.read_models import CaptureListRow
from ..domain.entities import Capture
from ..domain.value_objects import CaptureStatus
from .models import CaptureModel


class SqlAlchemyCaptureRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    @staticmethod
    def _to_domain(model: CaptureModel) -> Capture:
        return Capture(
            id=model.id,
            indicator_id=model.indicador_id,
            period_id=model.periodo_id,
            capturer_id=model.capturista_id,
            result=model.resultado,
            source_data=model.datos_fuente,
            activity=model.actividad_realizada,
            observations=model.observaciones,
            status=CaptureStatus(model.estado),
            progress_percentage=model.pct_avance,
            semaphore=model.semaforo,
            created_at=model.creado_en,
            updated_at=model.actualizado_en,
            version=model.version,
        )

    async def add(self, capture: Capture) -> None:
        now = datetime.now(UTC)
        async with session_scope(self.session_factory) as session:
            try:
                model = CaptureModel(
                    indicador_id=capture.indicator_id,
                    periodo_id=capture.period_id,
                    capturista_id=capture.capturer_id,
                    resultado=capture.result,
                    datos_fuente=capture.source_data,
                    actividad_realizada=capture.activity,
                    observaciones=capture.observations,
                    estado=capture.status.value,
                    creado_en=now,
                    actualizado_en=now,
                    version=capture.version,
                )
                session.add(model)
                await commit_or_flush(session)
            except IntegrityError as exc:
                await session.rollback()
                raise ConflictError("Ya existe una captura para el indicador y periodo.") from exc
        capture.id = model.id
        capture.created_at = now
        capture.updated_at = now

    async def get_by_id(self, capture_id: int) -> Capture | None:
        async with session_scope(self.session_factory) as session:
            model = await session.get(CaptureModel, capture_id)
            return self._to_domain(model) if model else None

    async def get_by_indicator_period(self, indicator_id: int, period_id: int) -> Capture | None:
        async with session_scope(self.session_factory) as session:
            model = (
                await session.execute(
                    select(CaptureModel).where(
                        CaptureModel.indicador_id == indicator_id,
                        CaptureModel.periodo_id == period_id,
                    )
                )
            ).scalar_one_or_none()
            return self._to_domain(model) if model else None

    async def update(self, capture: Capture) -> None:
        async with session_scope(self.session_factory) as session:
            result = await session.execute(
                update(CaptureModel)
                .where(CaptureModel.id == capture.id, CaptureModel.version == capture.version)
                .values(
                    resultado=capture.result,
                    datos_fuente=capture.source_data,
                    actividad_realizada=capture.activity,
                    observaciones=capture.observations,
                    estado=capture.status.value,
                    actualizado_en=capture.updated_at,
                    version=capture.version + 1,
                )
            )
            if result.rowcount != 1:
                current = await session.scalar(
                    select(CaptureModel.version).where(CaptureModel.id == capture.id)
                )
                raise ConflictError(
                    "La captura fue modificada por otra solicitud.",
                    details={"version_actual": current},
                )
            await commit_or_flush(session)
            capture.version += 1

    async def list_by_capturer(
        self,
        capturer_id: int,
        period_id: int | None = None,
    ) -> list[Capture]:
        async with session_scope(self.session_factory) as session:
            statement = select(CaptureModel).where(CaptureModel.capturista_id == capturer_id)
            if period_id is not None:
                statement = statement.where(CaptureModel.periodo_id == period_id)
            models = (await session.scalars(statement.order_by(CaptureModel.id))).all()
            return [self._to_domain(model) for model in models]

    async def list_by_indicator(self, indicator_id: int) -> list[Capture]:
        async with session_scope(self.session_factory) as session:
            models = (
                await session.scalars(
                    select(CaptureModel)
                    .where(
                        CaptureModel.indicador_id == indicator_id,
                        CaptureModel.estado == "validado",
                    )
                    .order_by(CaptureModel.periodo_id)
                )
            ).all()
            return [self._to_domain(model) for model in models]

    async def update_evaluation(self, capture_id: int, progress_percentage, semaphore: str) -> None:
        async with session_scope(self.session_factory) as session:
            model = await session.get(CaptureModel, capture_id)
            if model is None:
                return
            model.pct_avance = progress_percentage
            model.semaforo = semaphore
            model.actualizado_en = datetime.now(UTC)
            model.version += 1
            await commit_or_flush(session)

    async def list_all(self) -> list[Capture]:
        async with session_scope(self.session_factory) as session:
            models = (await session.scalars(select(CaptureModel).order_by(CaptureModel.id))).all()
            return [self._to_domain(model) for model in models]

    async def list_page_enriched(
        self,
        *,
        status: str | None,
        area_id: int | None,
        indicator_id: int | None,
        period_id: int | None,
        query: str | None,
        from_date,
        to_date,
        capturer_id: int | None,
        allowed_capturer_id: int | None,
        sort: str,
        descending: bool,
        offset: int,
        limit: int,
    ) -> tuple[list[CaptureListRow], int]:
        evidence_count = (
            select(
                EvidenceLinkModel.entidad_id.label("capture_id"),
                func.count(EvidenceLinkModel.id).label("evidence_total"),
            )
            .where(EvidenceLinkModel.entidad == "captura")
            .group_by(EvidenceLinkModel.entidad_id)
            .subquery()
        )
        filters = []
        if status is not None:
            filters.append(CaptureModel.estado == status)
        if area_id is not None:
            filters.append(IndicatorModel.area_id == area_id)
        if indicator_id is not None:
            filters.append(CaptureModel.indicador_id == indicator_id)
        if period_id is not None:
            filters.append(CaptureModel.periodo_id == period_id)
        if capturer_id is not None:
            filters.append(CaptureModel.capturista_id == capturer_id)
        if allowed_capturer_id is not None:
            filters.append(CaptureModel.capturista_id == allowed_capturer_id)
        if from_date is not None:
            filters.append(func.date(CaptureModel.actualizado_en) >= from_date)
        if to_date is not None:
            filters.append(func.date(CaptureModel.actualizado_en) <= to_date)
        if query:
            pattern = f"%{query.strip()}%"
            filters.append(
                or_(
                    IndicatorModel.clave.ilike(pattern),
                    IndicatorModel.nombre.ilike(pattern),
                    UserModel.nombre.ilike(pattern),
                )
            )

        base = (
            select(CaptureModel.id)
            .join(IndicatorModel, IndicatorModel.id == CaptureModel.indicador_id)
            .join(UserModel, UserModel.id == CaptureModel.capturista_id)
            .where(*filters)
        )
        async with session_scope(self.session_factory) as session:
            total = int(
                await session.scalar(select(func.count()).select_from(base.subquery())) or 0
            )
            sort_column = {
                "actualizado_en": CaptureModel.actualizado_en,
                "estado": CaptureModel.estado,
                "indicador": IndicatorModel.clave,
                "periodo": PeriodModel.fecha_inicio,
                "capturista": UserModel.nombre,
                "porcentaje_avance": CaptureModel.pct_avance,
            }[sort]
            direction = sort_column.desc() if descending else sort_column.asc()
            id_direction = CaptureModel.id.desc() if descending else CaptureModel.id.asc()
            statement = (
                select(
                    CaptureModel.id,
                    IndicatorModel.id.label("indicator_id"),
                    IndicatorModel.clave.label("indicator_key"),
                    IndicatorModel.nombre.label("indicator_name"),
                    IndicatorModel.unidad_medida.label("indicator_unit"),
                    PeriodModel.id.label("period_id"),
                    PeriodModel.etiqueta.label("period_label"),
                    PeriodModel.estado.label("period_status"),
                    PeriodModel.fecha_limite.label("period_deadline"),
                    AreaModel.id.label("area_id"),
                    AreaModel.codigo.label("area_code"),
                    AreaModel.nombre.label("area_name"),
                    AreaModel.color.label("area_color"),
                    UserModel.id.label("capturer_id"),
                    UserModel.nombre.label("capturer_name"),
                    UserModel.correo.label("capturer_email"),
                    CaptureModel.resultado.label("result"),
                    GoalModel.valor.label("goal"),
                    CaptureModel.pct_avance.label("progress_percentage"),
                    CaptureModel.semaforo.label("semaphore"),
                    CaptureModel.estado.label("status"),
                    func.coalesce(evidence_count.c.evidence_total, 0).label(
                        "evidence_total"
                    ),
                    CaptureModel.actualizado_en.label("updated_at"),
                )
                .join(IndicatorModel, IndicatorModel.id == CaptureModel.indicador_id)
                .join(PeriodModel, PeriodModel.id == CaptureModel.periodo_id)
                .join(AreaModel, AreaModel.id == IndicatorModel.area_id)
                .join(UserModel, UserModel.id == CaptureModel.capturista_id)
                .outerjoin(
                    GoalModel,
                    (GoalModel.indicador_id == CaptureModel.indicador_id)
                    & (GoalModel.periodo_id == CaptureModel.periodo_id),
                )
                .outerjoin(evidence_count, evidence_count.c.capture_id == CaptureModel.id)
                .where(*filters)
                .order_by(direction, id_direction)
                .offset(offset)
                .limit(limit)
            )
            rows = (await session.execute(statement)).mappings().all()
            return [CaptureListRow(**dict(row)) for row in rows], total

    async def reset_validated_for_period(self, period_id: int, actor_id: int) -> list[int]:
        del actor_id
        reset_ids = []
        async with session_scope(self.session_factory) as session:
            models = await session.scalars(
                select(CaptureModel).where(
                    CaptureModel.periodo_id == period_id,
                    CaptureModel.estado == "validado",
                )
            )
            for model in models:
                reset_ids.append(model.id)
                model.estado = "borrador"
                model.pct_avance = None
                model.semaforo = None
                model.actualizado_en = datetime.now(UTC)
                model.version += 1
            await commit_or_flush(session)
        return reset_ids
