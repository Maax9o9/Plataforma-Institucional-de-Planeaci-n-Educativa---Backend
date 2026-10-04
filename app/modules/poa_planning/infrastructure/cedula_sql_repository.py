"""Adaptador PostgreSQL para catálogos, cédulas y emisiones POA."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.indicators_capture.domain.value_objects import CaptureStatus
from app.shared.domain.exceptions import ConflictError
from app.shared.infrastructure.db.unit_of_work import commit_or_flush, session_scope

from ..domain.cedula_entities import (
    PoaActivityCatalog,
    PoaActivityFollowUp,
    PoaFollowUpCard,
    PoaForm,
    PoaFormActivity,
    PoaFormDetail,
    PoaFormIndicator,
    PoaFormIssue,
    PoaFormQuarter,
    PoaIndicatorCatalog,
    PoaObjectiveCatalog,
    PoaSignatory,
    PoaStrategyCatalog,
)
from .cedula_models import (
    PoaActivityCatalogModel,
    PoaActivityFollowUpModel,
    PoaFormActivityCriteriaModel,
    PoaFormActivityModel,
    PoaFormIndicatorModel,
    PoaFormIssueModel,
    PoaFormModel,
    PoaFormQuarterModel,
    PoaIndicatorCatalogModel,
    PoaObjectiveCatalogModel,
    PoaStrategyCatalogModel,
)
from .reference_data import (
    POA_ACTIVITIES,
    POA_INDICATORS,
    POA_OBJECTIVES,
    POA_STRATEGIES,
)


def _catalog_key(item) -> tuple[int, ...]:
    return tuple(int(part) for part in item.key.split("."))


async def _load_activity_criteria(
    session: AsyncSession, activity_ids: list[int]
) -> dict[int, list[int]]:
    """Trae, en una sola consulta, los criterios SEAES de varias actividades.

    Pedirlos actividad por actividad dentro de una comprensión sería N+1.
    """
    if not activity_ids:
        return {}
    rows = await session.execute(
        select(
            PoaFormActivityCriteriaModel.cedula_actividad_id,
            PoaFormActivityCriteriaModel.criterio_seaes_id,
        )
        .where(PoaFormActivityCriteriaModel.cedula_actividad_id.in_(activity_ids))
        .order_by(
            PoaFormActivityCriteriaModel.cedula_actividad_id,
            PoaFormActivityCriteriaModel.criterio_seaes_id,
        )
    )
    grouped: dict[int, list[int]] = {}
    for activity_id, criterio_id in rows.all():
        grouped.setdefault(activity_id, []).append(criterio_id)
    return grouped


class SqlAlchemyPoaFormRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def ensure_catalogs(self) -> None:
        async with session_scope(self.session_factory) as session:
            statements = (
                pg_insert(PoaObjectiveCatalogModel)
                .values(list(POA_OBJECTIVES))
                .on_conflict_do_nothing(index_elements=["numero"]),
                pg_insert(PoaStrategyCatalogModel)
                .values(list(POA_STRATEGIES))
                .on_conflict_do_nothing(index_elements=["clave"]),
                pg_insert(PoaIndicatorCatalogModel)
                .values(list(POA_INDICATORS))
                .on_conflict_do_nothing(index_elements=["clave"]),
                pg_insert(PoaActivityCatalogModel)
                .values(list(POA_ACTIVITIES))
                .on_conflict_do_nothing(index_elements=["clave"]),
            )
            for statement in statements:
                await session.execute(statement)
            await commit_or_flush(session)

    async def list_objectives(self) -> list[PoaObjectiveCatalog]:
        async with session_scope(self.session_factory) as session:
            models = (
                await session.scalars(
                    select(PoaObjectiveCatalogModel).order_by(PoaObjectiveCatalogModel.numero)
                )
            ).all()
            return [self._objective(model) for model in models]

    async def list_strategies(
        self, *, objective_number: int | None = None
    ) -> list[PoaStrategyCatalog]:
        async with session_scope(self.session_factory) as session:
            statement = select(PoaStrategyCatalogModel).order_by(PoaStrategyCatalogModel.clave)
            if objective_number is not None:
                statement = statement.where(
                    PoaStrategyCatalogModel.objetivo_numero == objective_number
                )
            items = [self._strategy(model) for model in (await session.scalars(statement)).all()]
            return sorted(items, key=_catalog_key)

    async def get_strategy(self, key: str) -> PoaStrategyCatalog | None:
        async with session_scope(self.session_factory) as session:
            model = await session.get(PoaStrategyCatalogModel, key)
            return self._strategy(model) if model else None

    async def list_indicators(
        self, *, objective_number: int | None = None
    ) -> list[PoaIndicatorCatalog]:
        async with session_scope(self.session_factory) as session:
            statement = select(PoaIndicatorCatalogModel).order_by(PoaIndicatorCatalogModel.clave)
            if objective_number is not None:
                statement = statement.where(
                    PoaIndicatorCatalogModel.objetivo_numero == objective_number
                )
            items = [self._indicator(model) for model in (await session.scalars(statement)).all()]
            return sorted(items, key=_catalog_key)

    async def get_indicator(self, key: str) -> PoaIndicatorCatalog | None:
        async with session_scope(self.session_factory) as session:
            model = await session.get(PoaIndicatorCatalogModel, key)
            return self._indicator(model) if model else None

    async def list_activity_catalog(
        self, *, strategy_key: str | None = None
    ) -> list[PoaActivityCatalog]:
        async with session_scope(self.session_factory) as session:
            statement = select(PoaActivityCatalogModel).order_by(PoaActivityCatalogModel.clave)
            if strategy_key is not None:
                statement = statement.where(
                    PoaActivityCatalogModel.estrategia_clave == strategy_key
                )
            items = [
                self._activity_catalog(model) for model in (await session.scalars(statement)).all()
            ]
            return sorted(items, key=_catalog_key)

    async def get_activity_catalog(self, key: str) -> PoaActivityCatalog | None:
        async with session_scope(self.session_factory) as session:
            model = await session.get(PoaActivityCatalogModel, key)
            return self._activity_catalog(model) if model else None

    async def add_form(self, item: PoaForm) -> None:
        now = datetime.now(UTC)
        async with session_scope(self.session_factory) as session:
            try:
                model = PoaFormModel(
                    ejercicio_id=item.exercise_id,
                    objetivo_numero=item.objective_number,
                    estrategia_clave=item.strategy_key,
                    area_responsable_id=item.responsible_area_id,
                    alcance_efecto_socioeconomico=item.scope_and_socioeconomic_effect,
                    tipo_estrategia=item.strategy_type,
                    firmantes=[asdict(s) for s in item.signatories],
                    creado_por=item.created_by,
                    version=item.version,
                    creado_en=now,
                    actualizado_en=now,
                )
                session.add(model)
                await session.flush()
                await commit_or_flush(session)
            except IntegrityError as exc:
                await session.rollback()
                raise ConflictError(
                    "Ya existe una cédula para la estrategia, área y ejercicio."
                ) from exc
        item.id = model.id
        item.created_at = now
        item.updated_at = now

    async def get_form(self, item_id: int) -> PoaForm | None:
        async with session_scope(self.session_factory) as session:
            model = await session.get(PoaFormModel, item_id)
            return self._form(model) if model else None

    async def update_form(self, item: PoaForm) -> None:
        try:
            async with session_scope(self.session_factory) as session:
                result = await session.execute(
                    update(PoaFormModel)
                    .where(PoaFormModel.id == item.id, PoaFormModel.version == item.version)
                    .values(
                        objetivo_numero=item.objective_number,
                        estrategia_clave=item.strategy_key,
                        area_responsable_id=item.responsible_area_id,
                        alcance_efecto_socioeconomico=item.scope_and_socioeconomic_effect,
                        tipo_estrategia=item.strategy_type,
                        firmantes=[asdict(s) for s in item.signatories],
                        version=item.version + 1,
                        actualizado_en=item.updated_at,
                    )
                )
                if result.rowcount != 1:
                    raise ConflictError("La cédula fue modificada por otra solicitud.")
                await commit_or_flush(session)
            item.version += 1
        except IntegrityError as exc:
            raise ConflictError(
                "Ya existe una cédula para la estrategia, área y ejercicio.",
                details={"reason": "POA_FORM_DUPLICATE", "field": "area_responsable_id"},
            ) from exc

    async def delete_form(self, item_id: int) -> None:
        # `poa_cedula_indicadores`, `poa_cedula_actividades` y
        # `poa_cedula_cuatrimestres` tienen ON DELETE CASCADE hacia esta tabla
        # (migraciones 0022 y 0023), y a su vez arrastran seguimientos y
        # criterios SEAES de cada actividad. `poa_cedula_emisiones` es la
        # excepción a propósito -no tiene cascada-: el caso de uso ya comprobó
        # que no hay emisiones antes de llamar aquí, pero si algo se le
        # adelantara (una emisión creada justo entre la comprobación y este
        # DELETE), Postgres frena el borrado con un IntegrityError en vez de
        # dejar un respaldo institucional sin cédula.
        async with session_scope(self.session_factory) as session:
            try:
                await session.execute(delete(PoaFormModel).where(PoaFormModel.id == item_id))
                await commit_or_flush(session)
            except IntegrityError as exc:
                await session.rollback()
                raise ConflictError(
                    "La cédula ya fue emitida en algún cuatrimestre; no puede eliminarse.",
                    details={"reason": "POA_FORM_HAS_ISSUES", "cedula_id": item_id},
                ) from exc

    async def add_form_quarter(self, item: PoaFormQuarter) -> None:
        async with session_scope(self.session_factory) as session:
            try:
                model = PoaFormQuarterModel(
                    cedula_id=item.form_id,
                    cuatrimestre=item.quarter,
                    periodo_id=item.period_id,
                    fecha_inicio=item.starts_on,
                    fecha_fin=item.ends_on,
                )
                session.add(model)
                await session.flush()
                await commit_or_flush(session)
            except IntegrityError as exc:
                await session.rollback()
                raise ConflictError("El cuatrimestre ya está configurado para la cédula.") from exc
        item.id = model.id

    async def list_form_quarters(self, form_id: int) -> list[PoaFormQuarter]:
        async with session_scope(self.session_factory) as session:
            models = (
                await session.scalars(
                    select(PoaFormQuarterModel)
                    .where(PoaFormQuarterModel.cedula_id == form_id)
                    .order_by(PoaFormQuarterModel.cuatrimestre)
                )
            ).all()
            return [self._form_quarter(model) for model in models]

    async def list_forms(
        self,
        *,
        exercise_id: int | None = None,
        objective_number: int | None = None,
        responsible_area_id: int | None = None,
    ) -> list[PoaForm]:
        async with session_scope(self.session_factory) as session:
            statement = select(PoaFormModel).order_by(PoaFormModel.id)
            if exercise_id is not None:
                statement = statement.where(PoaFormModel.ejercicio_id == exercise_id)
            if objective_number is not None:
                statement = statement.where(PoaFormModel.objetivo_numero == objective_number)
            if responsible_area_id is not None:
                statement = statement.where(PoaFormModel.area_responsable_id == responsible_area_id)
            return [self._form(model) for model in (await session.scalars(statement)).all()]

    async def add_form_indicator(self, item: PoaFormIndicator) -> None:
        now = datetime.now(UTC)
        async with session_scope(self.session_factory) as session:
            try:
                model = PoaFormIndicatorModel(
                    cedula_id=item.form_id,
                    indicador_clave=item.indicator_key,
                    meta_institucional=item.institutional_goal,
                    linea_base_anio=item.baseline_year,
                    linea_base_valor=item.baseline_value,
                    porcentaje_actual=item.current_percentage,
                    meta_numero=item.target_value,
                    meta_porcentaje=item.target_percentage,
                    total_alcanzado=item.total_achieved,
                    porcentaje_alcanzado=item.achieved_percentage,
                    creado_en=now,
                    actualizado_en=now,
                )
                session.add(model)
                await session.flush()
                await commit_or_flush(session)
            except IntegrityError as exc:
                await session.rollback()
                raise ConflictError("El indicador ya está asociado a la cédula.") from exc
        item.id = model.id
        item.created_at = now
        item.updated_at = now

    async def get_form_indicator(self, item_id: int) -> PoaFormIndicator | None:
        async with session_scope(self.session_factory) as session:
            model = await session.get(PoaFormIndicatorModel, item_id)
            return self._form_indicator(model) if model else None

    async def update_form_indicator(self, item: PoaFormIndicator) -> None:
        async with session_scope(self.session_factory) as session:
            model = await session.get(PoaFormIndicatorModel, item.id)
            if model is None:
                return
            model.meta_institucional = item.institutional_goal
            model.linea_base_anio = item.baseline_year
            model.linea_base_valor = item.baseline_value
            model.porcentaje_actual = item.current_percentage
            model.meta_numero = item.target_value
            model.meta_porcentaje = item.target_percentage
            model.total_alcanzado = item.total_achieved
            model.porcentaje_alcanzado = item.achieved_percentage
            model.actualizado_en = item.updated_at
            await commit_or_flush(session)

    async def delete_form_indicator(self, item_id: int) -> None:
        async with session_scope(self.session_factory) as session:
            await session.execute(
                delete(PoaFormIndicatorModel).where(PoaFormIndicatorModel.id == item_id)
            )
            await commit_or_flush(session)

    async def add_form_activity(self, item: PoaFormActivity) -> None:
        now = datetime.now(UTC)
        async with session_scope(self.session_factory) as session:
            try:
                model = PoaFormActivityModel(
                    cedula_id=item.form_id,
                    actividad_clave=item.activity_key,
                    unidad_medida=item.unit,
                    meta_anual=item.annual_goal,
                    area_ejecutora_id=item.executing_area_id,
                    observaciones=item.observations,
                    actividad_upe=item.upe_description,
                    creado_en=now,
                    actualizado_en=now,
                )
                session.add(model)
                await session.flush()
                await commit_or_flush(session)
            except IntegrityError as exc:
                await session.rollback()
                raise ConflictError("La actividad ya está asociada a la cédula.") from exc
        item.id = model.id
        item.created_at = now
        item.updated_at = now

    async def get_form_activity(self, item_id: int) -> PoaFormActivity | None:
        async with session_scope(self.session_factory) as session:
            model = await session.get(PoaFormActivityModel, item_id)
            if model is None:
                return None
            criteria = await _load_activity_criteria(session, [item_id])
            return self._form_activity(model, criteria.get(item_id, []))

    async def update_form_activity(self, item: PoaFormActivity) -> None:
        async with session_scope(self.session_factory) as session:
            model = await session.get(PoaFormActivityModel, item.id)
            if model is None:
                return
            model.unidad_medida = item.unit
            model.meta_anual = item.annual_goal
            model.area_ejecutora_id = item.executing_area_id
            model.observaciones = item.observations
            model.actividad_upe = item.upe_description
            model.actualizado_en = item.updated_at
            await commit_or_flush(session)

    async def delete_form_activity(self, item_id: int) -> None:
        # `poa_cedula_seguimientos` y `poa_cedula_actividad_criterios` tienen
        # ON DELETE CASCADE hacia esta tabla (migraciones 0022, 0023 y 0031):
        # borran sus seguimientos y criterios SEAES solos. El caso de uso ya
        # comprobó que la actividad no tiene seguimientos capturados.
        async with session_scope(self.session_factory) as session:
            await session.execute(
                delete(PoaFormActivityModel).where(PoaFormActivityModel.id == item_id)
            )
            await commit_or_flush(session)

    async def replace_activity_criteria(
        self, form_activity_id: int, criteria_seaes_ids: tuple[int, ...], updated_at: datetime
    ) -> None:
        """Reemplaza el conjunto completo de criterios: borra y vuelve a insertar.

        Va aparte de `update_form_activity` porque es una tabla distinta
        (muchos a muchos) y una acción auditable propia, no un campo más de
        la actividad.
        """
        async with session_scope(self.session_factory) as session:
            await session.execute(
                delete(PoaFormActivityCriteriaModel).where(
                    PoaFormActivityCriteriaModel.cedula_actividad_id == form_activity_id
                )
            )
            if criteria_seaes_ids:
                await session.execute(
                    pg_insert(PoaFormActivityCriteriaModel).values(
                        [
                            {
                                "cedula_actividad_id": form_activity_id,
                                "criterio_seaes_id": criterio_id,
                            }
                            for criterio_id in criteria_seaes_ids
                        ]
                    )
                )
            await session.execute(
                update(PoaFormActivityModel)
                .where(PoaFormActivityModel.id == form_activity_id)
                .values(actualizado_en=updated_at)
            )
            await commit_or_flush(session)

    async def get_follow_up(self, item_id: int) -> PoaActivityFollowUp | None:
        async with session_scope(self.session_factory) as session:
            model = await session.get(PoaActivityFollowUpModel, item_id)
            return self._follow_up(model) if model else None

    async def get_follow_up_by_quarter(
        self, form_activity_id: int, quarter: int
    ) -> PoaActivityFollowUp | None:
        async with session_scope(self.session_factory) as session:
            model = (
                await session.execute(
                    select(PoaActivityFollowUpModel).where(
                        PoaActivityFollowUpModel.cedula_actividad_id == form_activity_id,
                        PoaActivityFollowUpModel.cuatrimestre == quarter,
                    )
                )
            ).scalar_one_or_none()
            return self._follow_up(model) if model else None

    async def update_follow_up(self, item: PoaActivityFollowUp) -> None:
        async with session_scope(self.session_factory) as session:
            model = await session.get(PoaActivityFollowUpModel, item.id)
            if model is None:
                return
            model.justificacion_desviacion = item.deviation_justification
            model.estado = item.status.value
            model.comentario_revision = item.review_comment
            model.actualizado_en = item.updated_at
            await commit_or_flush(session)

    async def upsert_follow_up(self, item: PoaActivityFollowUp) -> PoaActivityFollowUp:
        now = datetime.now(UTC)
        async with session_scope(self.session_factory) as session:
            model = (
                await session.execute(
                    select(PoaActivityFollowUpModel).where(
                        PoaActivityFollowUpModel.cedula_actividad_id == item.form_activity_id,
                        PoaActivityFollowUpModel.cuatrimestre == item.quarter,
                    )
                )
            ).scalar_one_or_none()
            if model is None:
                model = PoaActivityFollowUpModel(
                    cedula_actividad_id=item.form_activity_id,
                    cuatrimestre=item.quarter,
                    creado_en=now,
                    actualizado_en=now,
                )
                session.add(model)
            model.periodo_id = item.period_id
            model.capturado_por = item.captured_by
            model.programado = item.scheduled
            model.alcanzado = item.achieved
            model.justificacion_desviacion = item.deviation_justification
            model.progreso = item.progress
            model.alcance = item.scope
            model.estado = item.status.value
            model.comentario_revision = item.review_comment
            model.actualizado_en = now
            await session.flush()
            await commit_or_flush(session)
        item.id = model.id
        item.created_at = model.creado_en
        item.updated_at = now
        return item

    async def list_follow_up_cards(
        self,
        *,
        exercise_id: int | None = None,
        quarter: int | None = None,
        executing_area_id: int | None = None,
        status: str | None = None,
        offset: int = 0,
        limit: int = 200,
    ) -> tuple[list[PoaFollowUpCard], int]:
        async with session_scope(self.session_factory) as session:
            statement = (
                select(PoaActivityFollowUpModel, PoaFormActivityModel, PoaFormModel)
                .join(
                    PoaFormActivityModel,
                    PoaActivityFollowUpModel.cedula_actividad_id == PoaFormActivityModel.id,
                )
                .join(PoaFormModel, PoaFormActivityModel.cedula_id == PoaFormModel.id)
            )
            if exercise_id is not None:
                statement = statement.where(PoaFormModel.ejercicio_id == exercise_id)
            if quarter is not None:
                statement = statement.where(PoaActivityFollowUpModel.cuatrimestre == quarter)
            if executing_area_id is not None:
                statement = statement.where(
                    PoaFormActivityModel.area_ejecutora_id == executing_area_id
                )
            if status is not None:
                statement = statement.where(PoaActivityFollowUpModel.estado == status)
            total = await session.scalar(
                select(func.count()).select_from(statement.subquery())
            )
            rows = (
                await session.execute(
                    statement.order_by(
                        PoaFormActivityModel.actividad_clave,
                        PoaActivityFollowUpModel.cuatrimestre,
                    ).offset(offset).limit(limit)
                )
            ).all()
            criteria_by_activity = await _load_activity_criteria(
                session, [activity.id for _, activity, _ in rows]
            )
            return [
                PoaFollowUpCard(
                    id=follow_up.id,
                    form_id=form.id,
                    activity_id=activity.id,
                    activity_key=activity.actividad_clave,
                    unit=activity.unidad_medida,
                    annual_goal=activity.meta_anual,
                    executing_area_id=activity.area_ejecutora_id,
                    criteria_seaes_ids=tuple(criteria_by_activity.get(activity.id, [])),
                    quarter=follow_up.cuatrimestre,
                    period_id=follow_up.periodo_id,
                    scheduled=follow_up.programado,
                    achieved=follow_up.alcanzado,
                    status=CaptureStatus(follow_up.estado),
                    review_comment=follow_up.comentario_revision,
                    deviation_justification=follow_up.justificacion_desviacion,
                    progress=follow_up.progreso,
                    scope=follow_up.alcance,
                    updated_at=follow_up.actualizado_en,
                )
                for follow_up, activity, form in rows
            ], total or 0

    async def get_detail(self, form_id: int) -> PoaFormDetail | None:
        async with session_scope(self.session_factory) as session:
            form_model = await session.get(PoaFormModel, form_id)
            if form_model is None:
                return None
            indicator_models = (
                await session.scalars(
                    select(PoaFormIndicatorModel)
                    .where(PoaFormIndicatorModel.cedula_id == form_id)
                    .order_by(PoaFormIndicatorModel.id)
                )
            ).all()
            activity_models = (
                await session.scalars(
                    select(PoaFormActivityModel)
                    .where(PoaFormActivityModel.cedula_id == form_id)
                    .order_by(PoaFormActivityModel.id)
                )
            ).all()
            activity_ids = [model.id for model in activity_models]
            criteria_by_activity = await _load_activity_criteria(session, activity_ids)
            follow_up_models = []
            if activity_ids:
                follow_up_models = (
                    await session.scalars(
                        select(PoaActivityFollowUpModel)
                        .where(PoaActivityFollowUpModel.cedula_actividad_id.in_(activity_ids))
                        .order_by(
                            PoaActivityFollowUpModel.cedula_actividad_id,
                            PoaActivityFollowUpModel.cuatrimestre,
                        )
                    )
                ).all()
            return PoaFormDetail(
                form=self._form(form_model),
                quarters=await self.list_form_quarters(form_id),
                indicators=[self._form_indicator(model) for model in indicator_models],
                activities=[
                    self._form_activity(model, criteria_by_activity.get(model.id, []))
                    for model in activity_models
                ],
                follow_ups=[self._follow_up(model) for model in follow_up_models],
            )

    async def add_issue(self, item: PoaFormIssue) -> None:
        async with session_scope(self.session_factory) as session:
            try:
                model = PoaFormIssueModel(
                    cedula_id=item.form_id,
                    cuatrimestre=item.quarter,
                    periodo_id=item.period_id,
                    nombre=item.name,
                    snapshot=item.snapshot,
                    emitido_por=item.issued_by,
                    emitido_en=item.issued_at,
                )
                session.add(model)
                await session.flush()
                await commit_or_flush(session)
            except IntegrityError as exc:
                await session.rollback()
                raise ConflictError("La cédula ya fue emitida para ese cuatrimestre.") from exc
        item.id = model.id

    async def list_issues(self, form_id: int) -> list[PoaFormIssue]:
        async with session_scope(self.session_factory) as session:
            models = (
                await session.scalars(
                    select(PoaFormIssueModel)
                    .where(PoaFormIssueModel.cedula_id == form_id)
                    .order_by(PoaFormIssueModel.cuatrimestre)
                )
            ).all()
            return [self._issue(model) for model in models]

    async def get_issue(self, issue_id: int) -> PoaFormIssue | None:
        async with session_scope(self.session_factory) as session:
            model = await session.get(PoaFormIssueModel, issue_id)
            return self._issue(model) if model else None

    @staticmethod
    def _objective(model: PoaObjectiveCatalogModel) -> PoaObjectiveCatalog:
        return PoaObjectiveCatalog(
            key=model.clave,
            number=model.numero,
            denomination=model.denominacion,
            is_active=model.activo,
        )

    @staticmethod
    def _strategy(model: PoaStrategyCatalogModel) -> PoaStrategyCatalog:
        return PoaStrategyCatalog(
            key=model.clave,
            objective_number=model.objetivo_numero,
            denomination=model.denominacion,
            is_active=model.activo,
        )

    @staticmethod
    def _indicator(model: PoaIndicatorCatalogModel) -> PoaIndicatorCatalog:
        return PoaIndicatorCatalog(
            key=model.clave,
            objective_number=model.objetivo_numero,
            name=model.nombre,
            formula=model.formula,
            unit=model.unidad_medida,
            is_active=model.activo,
        )

    @staticmethod
    def _activity_catalog(model: PoaActivityCatalogModel) -> PoaActivityCatalog:
        return PoaActivityCatalog(
            key=model.clave,
            strategy_key=model.estrategia_clave,
            description=model.descripcion,
            is_active=model.activo,
        )

    @staticmethod
    def _form(model: PoaFormModel) -> PoaForm:
        return PoaForm(
            id=model.id,
            exercise_id=model.ejercicio_id,
            objective_number=model.objetivo_numero,
            strategy_key=model.estrategia_clave,
            responsible_area_id=model.area_responsable_id,
            scope_and_socioeconomic_effect=model.alcance_efecto_socioeconomico,
            strategy_type=model.tipo_estrategia,
            signatories=tuple(PoaSignatory(**s) for s in model.firmantes),
            created_by=model.creado_por,
            version=model.version,
            created_at=model.creado_en,
            updated_at=model.actualizado_en,
        )

    @staticmethod
    def _form_quarter(model: PoaFormQuarterModel) -> PoaFormQuarter:
        return PoaFormQuarter(
            id=model.id,
            form_id=model.cedula_id,
            quarter=model.cuatrimestre,
            period_id=model.periodo_id,
            starts_on=model.fecha_inicio,
            ends_on=model.fecha_fin,
        )

    @staticmethod
    def _form_indicator(model: PoaFormIndicatorModel) -> PoaFormIndicator:
        return PoaFormIndicator(
            id=model.id,
            form_id=model.cedula_id,
            indicator_key=model.indicador_clave,
            institutional_goal=model.meta_institucional,
            baseline_year=model.linea_base_anio,
            baseline_value=model.linea_base_valor,
            current_percentage=model.porcentaje_actual,
            target_value=model.meta_numero,
            target_percentage=model.meta_porcentaje,
            total_achieved=model.total_alcanzado,
            achieved_percentage=model.porcentaje_alcanzado,
            created_at=model.creado_en,
            updated_at=model.actualizado_en,
        )

    @staticmethod
    def _form_activity(
        model: PoaFormActivityModel, criteria_ids: list[int] | None = None
    ) -> PoaFormActivity:
        return PoaFormActivity(
            id=model.id,
            form_id=model.cedula_id,
            activity_key=model.actividad_clave,
            unit=model.unidad_medida,
            annual_goal=model.meta_anual,
            executing_area_id=model.area_ejecutora_id,
            observations=model.observaciones,
            upe_description=model.actividad_upe,
            criteria_seaes_ids=tuple(criteria_ids or ()),
            created_at=model.creado_en,
            updated_at=model.actualizado_en,
        )

    @staticmethod
    def _follow_up(model: PoaActivityFollowUpModel) -> PoaActivityFollowUp:
        return PoaActivityFollowUp(
            id=model.id,
            form_activity_id=model.cedula_actividad_id,
            quarter=model.cuatrimestre,
            period_id=model.periodo_id,
            captured_by=model.capturado_por,
            scheduled=model.programado,
            achieved=model.alcanzado,
            deviation_justification=model.justificacion_desviacion,
            progress=model.progreso,
            scope=model.alcance,
            status=CaptureStatus(model.estado),
            review_comment=model.comentario_revision,
            created_at=model.creado_en,
            updated_at=model.actualizado_en,
        )

    @staticmethod
    def _issue(model: PoaFormIssueModel) -> PoaFormIssue:
        return PoaFormIssue(
            id=model.id,
            form_id=model.cedula_id,
            quarter=model.cuatrimestre,
            period_id=model.periodo_id,
            name=model.nombre,
            snapshot=model.snapshot,
            issued_by=model.emitido_por,
            issued_at=model.emitido_en,
            created_at=model.emitido_en,
            updated_at=model.emitido_en,
        )
