"""Casos de uso de la cédula institucional y sus respaldos cuatrimestrales."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.shared.application.actor import ActorContext
from app.shared.application.event_bus import EventBus
from app.shared.domain.exceptions import (
    ForbiddenError,
    InvalidStateError,
    ResourceNotFoundError,
    ValidationError,
)

from ....evidence_management.domain.ports.repositories import EvidenceRepository
from ....evidence_management.domain.value_objects import EvidenceType, FlowEntity
from ....institutional_catalogs.domain.ports.repositories import AreaRepository
from ....periods.domain.entities import Period
from ....periods.domain.ports.repository import PeriodRepository
from ....periods.domain.value_objects import PeriodStatus, PeriodType
from ...domain.cedula_entities import (
    PoaActivityFollowUp,
    PoaForm,
    PoaFormActivity,
    PoaFormDetail,
    PoaFormIndicator,
    PoaFormIssue,
    PoaFormQuarter,
    build_issue_name,
    four_month_period_name,
)
from ...domain.events import PoaStructureChanged
from ...domain.ports.cedula_repository import PoaFormRepository
from ...domain.ports.repositories import PoaRepository
from ..access_control import can_capture_activity, ensure_planning, ensure_structure_access
from ..cedula_dto import (
    AddPoaFormActivityCommand,
    AddPoaFormIndicatorCommand,
    CapturePoaIndicatorTotalCommand,
    CreatePoaFormCommand,
    IssuePoaFormCommand,
    RecordPoaFollowUpCommand,
    UpdatePoaFollowUpJustificationCommand,
    UpdatePoaFormActivityCommand,
    UpdatePoaFormCommand,
    UpdatePoaFormIndicatorCommand,
)


def _today() -> date:
    return date.today()


def _ensure_follow_up_access(
    form: PoaForm,
    activity: PoaFormActivity,
    actor: ActorContext,
) -> None:
    if not can_capture_activity(actor, activity.executing_area_id):
        raise ForbiddenError("La actividad POA no está asignada al área del usuario.")


def _can_override_structure_lock(actor: ActorContext) -> bool:
    return actor.has_any_role("admin_sistema", "planeacion_admin")


async def _ensure_structure_editable(
    repository: PoaFormRepository,
    form: PoaForm,
    actor: ActorContext,
) -> None:
    if _can_override_structure_lock(actor):
        return
    quarters = await repository.list_form_quarters(form.id)
    first_quarter = next((item for item in quarters if item.quarter == 1), None)
    if first_quarter is None:
        raise InvalidStateError("La cédula no tiene configurado el primer cuatrimestre.")
    if _today() > first_quarter.ends_on:
        raise InvalidStateError(
            "La estructura de la cédula quedó cerrada al finalizar el primer cuatrimestre."
        )


async def _require_form(repository: PoaFormRepository, form_id: int) -> PoaForm:
    form = await repository.get_form(form_id)
    if form is None:
        raise ResourceNotFoundError("La cédula POA no existe.")
    return form


async def _validate_period(
    *,
    repository: PoaFormRepository,
    periods: PeriodRepository,
    exercises: PoaRepository,
    form: PoaForm,
    period_id: int,
    quarter: int,
) -> None:
    schedules = await repository.list_form_quarters(form.id)
    schedule = next((item for item in schedules if item.quarter == quarter), None)
    if schedule is None or schedule.period_id != period_id:
        raise ValidationError("El periodo no corresponde al cuatrimestre de la cédula.")
    period = await periods.get_by_id(period_id)
    if period is None:
        raise ResourceNotFoundError("El periodo POA no existe.")
    if period.status is not PeriodStatus.OPEN:
        raise InvalidStateError("El periodo POA debe estar abierto.")
    if period.period_type is not PeriodType.POA:
        raise ValidationError("La cédula requiere un periodo de tipo POA.")
    exercise = await exercises.get_exercise(form.exercise_id)
    if exercise is None:
        raise ResourceNotFoundError("El ejercicio POA de la cédula no existe.")
    if period.year != exercise.year:
        raise ValidationError("El periodo no pertenece al ejercicio de la cédula.")
    if period.starts_on != schedule.starts_on or period.ends_on != schedule.ends_on:
        raise ValidationError("Las fechas del periodo no coinciden con la cédula.")


async def _publish(
    event_bus: EventBus,
    *,
    actor_id: int,
    aggregate_type: str,
    aggregate_id: int,
    action: str,
    data: dict[str, Any],
) -> None:
    await event_bus.publish(
        PoaStructureChanged(
            actor_id=actor_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            action=action,
            data=data,
        )
    )


async def _has_file_evidence(
    evidences: EvidenceRepository,
    follow_up_id: int,
) -> bool:
    items = await evidences.list_for(FlowEntity.POA_FORM_FOLLOW_UP, follow_up_id)
    return any(item.evidence_type is EvidenceType.FILE for item in items)


class CreatePoaForm:
    def __init__(
        self,
        repository: PoaFormRepository,
        exercises: PoaRepository,
        areas: AreaRepository,
        event_bus: EventBus,
        periods: PeriodRepository,
        unit_of_work,
    ) -> None:
        self.repository = repository
        self.exercises = exercises
        self.areas = areas
        self.event_bus = event_bus
        self.periods = periods
        self.unit_of_work = unit_of_work

    async def execute(self, command: CreatePoaFormCommand) -> PoaForm:
        ensure_planning(command.actor)
        exercise = await self.exercises.get_exercise(command.exercise_id)
        if exercise is None:
            raise ResourceNotFoundError("El ejercicio POA no existe.")
        quarters = sorted(command.quarters, key=lambda item: item.quarter)
        if {item.quarter for item in quarters} != {1, 2, 3} or len(quarters) != 3:
            raise ValidationError("Debe indicar exactamente los tres cuatrimestres.")
        previous_end = None
        for quarter in quarters:
            four_month_period_name(quarter.quarter)
            if quarter.starts_on.year != exercise.year or quarter.ends_on.year != exercise.year:
                raise ValidationError("Todos los cuatrimestres deben pertenecer al ejercicio POA.")
            if quarter.ends_on <= quarter.starts_on:
                raise ValidationError("La fecha final debe ser posterior a la fecha inicial.")
            if previous_end is not None and quarter.starts_on <= previous_end:
                raise ValidationError("Los cuatrimestres deben estar ordenados y no traslaparse.")
            previous_end = quarter.ends_on
        if not _can_override_structure_lock(command.actor) and _today() > quarters[0].ends_on:
            raise InvalidStateError("No se puede crear una cédula después del primer cuatrimestre.")
        strategy = await self.repository.get_strategy(command.strategy_key)
        if strategy is None or not strategy.is_active:
            raise ResourceNotFoundError("La estrategia POA no existe o está desactivada.")
        area = await self.areas.get_by_id(command.responsible_area_id)
        if area is None or not area.is_active:
            raise ValidationError("El área responsable no existe o está desactivada.")
        item = PoaForm.create(
            exercise_id=command.exercise_id,
            objective_number=strategy.objective_number,
            strategy_key=strategy.key,
            responsible_area_id=command.responsible_area_id,
            created_by=command.actor.id,
            scope_and_socioeconomic_effect=command.scope_and_socioeconomic_effect,
        )
        async with self.unit_of_work():
            await self.repository.add_form(item)
            for quarter in quarters:
                period = Period.create(
                    name=(
                        f"Cédula {item.id} - {four_month_period_name(quarter.quarter)} "
                        f"{exercise.year}"
                    ),
                    starts_on=quarter.starts_on,
                    ends_on=quarter.ends_on,
                    period_type=PeriodType.POA,
                    periodicity=None,
                    year=exercise.year,
                )
                await self.periods.add(period)
                await self.repository.add_form_quarter(
                    PoaFormQuarter.create(
                        form_id=item.id,
                        quarter=quarter.quarter,
                        period_id=period.id,
                        starts_on=quarter.starts_on,
                        ends_on=quarter.ends_on,
                    )
                )
        await _publish(
            self.event_bus,
            actor_id=command.actor.id,
            aggregate_type="poa_form",
            aggregate_id=item.id,
            action="created",
            data={"strategy_key": item.strategy_key, "exercise_id": item.exercise_id},
        )
        return item


class UpdatePoaForm:
    def __init__(
        self,
        repository: PoaFormRepository,
        areas: AreaRepository,
        event_bus: EventBus,
    ) -> None:
        self.repository = repository
        self.areas = areas
        self.event_bus = event_bus

    async def execute(self, command: UpdatePoaFormCommand) -> PoaForm:
        form = await _require_form(self.repository, command.form_id)
        await ensure_structure_access(command.actor, self.areas)
        await _ensure_structure_editable(self.repository, form, command.actor)
        objective_number = None
        if command.strategy_key is not None and command.strategy_key != form.strategy_key:
            strategy = await self.repository.get_strategy(command.strategy_key)
            if strategy is None or not strategy.is_active:
                raise ResourceNotFoundError("La estrategia POA no existe o está desactivada.")
            detail = await self.repository.get_detail(form.id)
            assert detail is not None
            indicator_catalogs = {
                item.key: item for item in await self.repository.list_indicators()
            }
            activity_catalogs = {
                item.key: item for item in await self.repository.list_activity_catalog()
            }
            incompatible_indicators = [
                item.id
                for item in detail.indicators
                if indicator_catalogs[item.indicator_key].objective_number
                != strategy.objective_number
            ]
            incompatible_activities = [
                item.id
                for item in detail.activities
                if activity_catalogs[item.activity_key].strategy_key != strategy.key
            ]
            if incompatible_indicators or incompatible_activities:
                raise ValidationError(
                    "La nueva estrategia no es compatible con el contenido de la cédula.",
                    details={
                        "indicador_ids": incompatible_indicators,
                        "actividad_ids": incompatible_activities,
                    },
                )
            objective_number = strategy.objective_number
        if command.responsible_area_id is not None:
            area = await self.areas.get_by_id(command.responsible_area_id)
            if area is None or not area.is_active:
                raise ValidationError("El área responsable no existe o está desactivada.")
        form.update_details(
            objective_number=objective_number,
            strategy_key=command.strategy_key,
            responsible_area_id=command.responsible_area_id,
            scope_and_socioeconomic_effect=command.scope_and_socioeconomic_effect,
        )
        await self.repository.update_form(form)
        await _publish(
            self.event_bus,
            actor_id=command.actor.id,
            aggregate_type="poa_form",
            aggregate_id=form.id,
            action="updated",
            data={"emergency_override": _can_override_structure_lock(command.actor)},
        )
        return form


class AddPoaFormIndicator:
    def __init__(
        self, repository: PoaFormRepository, event_bus: EventBus, areas: AreaRepository
    ) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.areas = areas

    async def execute(self, command: AddPoaFormIndicatorCommand) -> PoaFormIndicator:
        form = await _require_form(self.repository, command.form_id)
        await ensure_structure_access(command.actor, self.areas)
        await _ensure_structure_editable(self.repository, form, command.actor)
        catalog = await self.repository.get_indicator(command.indicator_key)
        if catalog is None or not catalog.is_active:
            raise ResourceNotFoundError("El indicador POA no existe o está desactivado.")
        if catalog.objective_number != form.objective_number:
            raise ValidationError("El indicador no pertenece al objetivo de la cédula.")
        item = PoaFormIndicator.create(
            form_id=form.id,
            indicator_key=catalog.key,
            institutional_goal=command.institutional_goal,
            baseline_year=command.baseline_year,
            baseline_value=command.baseline_value,
            current_percentage=command.current_percentage,
            target_value=command.target_value,
            target_percentage=command.target_percentage,
        )
        await self.repository.add_form_indicator(item)
        await _publish(
            self.event_bus,
            actor_id=command.actor.id,
            aggregate_type="poa_form_indicator",
            aggregate_id=item.id,
            action="created",
            data={"form_id": form.id, "indicator_key": item.indicator_key},
        )
        return item


class UpdatePoaFormIndicator:
    def __init__(
        self, repository: PoaFormRepository, event_bus: EventBus, areas: AreaRepository
    ) -> None:
        self.repository = repository
        self.event_bus = event_bus
        self.areas = areas

    async def execute(self, command: UpdatePoaFormIndicatorCommand) -> PoaFormIndicator:
        item = await self.repository.get_form_indicator(command.form_indicator_id)
        if item is None:
            raise ResourceNotFoundError("El indicador de la cédula no existe.")
        form = await _require_form(self.repository, item.form_id)
        await ensure_structure_access(command.actor, self.areas)
        await _ensure_structure_editable(self.repository, form, command.actor)
        values = {
            key: value
            for key, value in {
                "institutional_goal": command.institutional_goal,
                "baseline_year": command.baseline_year,
                "baseline_value": command.baseline_value,
                "current_percentage": command.current_percentage,
                "target_value": command.target_value,
                "target_percentage": command.target_percentage,
            }.items()
            if value is not None
        }
        item.update_details(**values)
        await self.repository.update_form_indicator(item)
        await _publish(
            self.event_bus,
            actor_id=command.actor.id,
            aggregate_type="poa_form_indicator",
            aggregate_id=item.id,
            action="updated",
            data={"form_id": form.id},
        )
        return item


class CapturePoaIndicatorTotal:
    def __init__(
        self,
        repository: PoaFormRepository,
        periods: PeriodRepository,
        exercises: PoaRepository,
        event_bus: EventBus,
        areas: AreaRepository,
    ) -> None:
        self.repository = repository
        self.periods = periods
        self.exercises = exercises
        self.event_bus = event_bus
        self.areas = areas

    async def execute(self, command: CapturePoaIndicatorTotalCommand) -> PoaFormIndicator:
        item = await self.repository.get_form_indicator(command.form_indicator_id)
        if item is None:
            raise ResourceNotFoundError("El indicador de la cédula no existe.")
        form = await _require_form(self.repository, item.form_id)
        await ensure_structure_access(command.actor, self.areas)
        await _validate_period(
            repository=self.repository,
            periods=self.periods,
            exercises=self.exercises,
            form=form,
            period_id=command.period_id,
            quarter=3,
        )
        item.capture_total(
            total_achieved=command.total_achieved,
            achieved_percentage=command.achieved_percentage,
        )
        await self.repository.update_form_indicator(item)
        await _publish(
            self.event_bus,
            actor_id=command.actor.id,
            aggregate_type="poa_form_indicator",
            aggregate_id=item.id,
            action="total_captured",
            data={"form_id": form.id, "period_id": command.period_id},
        )
        return item


class AddPoaFormActivity:
    def __init__(
        self,
        repository: PoaFormRepository,
        areas: AreaRepository,
        event_bus: EventBus,
    ) -> None:
        self.repository = repository
        self.areas = areas
        self.event_bus = event_bus

    async def execute(self, command: AddPoaFormActivityCommand) -> PoaFormActivity:
        form = await _require_form(self.repository, command.form_id)
        await ensure_structure_access(command.actor, self.areas)
        await _ensure_structure_editable(self.repository, form, command.actor)
        catalog = await self.repository.get_activity_catalog(command.activity_key)
        if catalog is None or not catalog.is_active:
            raise ResourceNotFoundError("La actividad POA no existe o está desactivada.")
        if catalog.strategy_key != form.strategy_key:
            raise ValidationError("La actividad no pertenece a la estrategia de la cédula.")
        if command.executing_area_id is not None:
            area = await self.areas.get_by_id(command.executing_area_id)
            if area is None or not area.is_active:
                raise ValidationError("El área ejecutora no existe o está desactivada.")
        item = PoaFormActivity.create(
            form_id=form.id,
            activity_key=catalog.key,
            unit=command.unit,
            annual_goal=command.annual_goal,
            executing_area_id=command.executing_area_id,
            observations=command.observations,
        )
        await self.repository.add_form_activity(item)
        await _publish(
            self.event_bus,
            actor_id=command.actor.id,
            aggregate_type="poa_form_activity",
            aggregate_id=item.id,
            action="created",
            data={"form_id": form.id, "activity_key": item.activity_key},
        )
        return item


class UpdatePoaFormActivity:
    def __init__(
        self,
        repository: PoaFormRepository,
        areas: AreaRepository,
        event_bus: EventBus,
    ) -> None:
        self.repository = repository
        self.areas = areas
        self.event_bus = event_bus

    async def execute(self, command: UpdatePoaFormActivityCommand) -> PoaFormActivity:
        item = await self.repository.get_form_activity(command.form_activity_id)
        if item is None:
            raise ResourceNotFoundError("La actividad de la cédula no existe.")
        form = await _require_form(self.repository, item.form_id)
        await ensure_structure_access(command.actor, self.areas)
        await _ensure_structure_editable(self.repository, form, command.actor)
        if command.executing_area_id is not None:
            area = await self.areas.get_by_id(command.executing_area_id)
            if area is None or not area.is_active:
                raise ValidationError("El área ejecutora no existe o está desactivada.")
        item.update_details(
            unit=command.unit,
            annual_goal=command.annual_goal,
            executing_area_id=command.executing_area_id,
            observations=command.observations,
        )
        await self.repository.update_form_activity(item)
        await _publish(
            self.event_bus,
            actor_id=command.actor.id,
            aggregate_type="poa_form_activity",
            aggregate_id=item.id,
            action="updated",
            data={"form_id": form.id},
        )
        return item


class RecordPoaFollowUp:
    def __init__(
        self,
        repository: PoaFormRepository,
        periods: PeriodRepository,
        exercises: PoaRepository,
        event_bus: EventBus,
    ) -> None:
        self.repository = repository
        self.periods = periods
        self.exercises = exercises
        self.event_bus = event_bus

    async def execute(self, command: RecordPoaFollowUpCommand) -> PoaActivityFollowUp:
        activity = await self.repository.get_form_activity(command.form_activity_id)
        if activity is None:
            raise ResourceNotFoundError("La actividad de la cédula no existe.")
        form = await _require_form(self.repository, activity.form_id)
        _ensure_follow_up_access(form, activity, command.actor)
        await _validate_period(
            repository=self.repository,
            periods=self.periods,
            exercises=self.exercises,
            form=form,
            period_id=command.period_id,
            quarter=command.quarter,
        )
        # HU-08.01 y HU-08.04: una vez enviado, el seguimiento sale de las manos
        # del area; validado, sólo vuelve por reapertura formal.
        existente = await self.repository.get_follow_up_by_quarter(activity.id, command.quarter)
        if existente is not None:
            existente.ensure_editable()

        item = PoaActivityFollowUp.create(
            form_activity_id=activity.id,
            quarter=command.quarter,
            period_id=command.period_id,
            captured_by=command.actor.id,
            scheduled=command.scheduled,
            achieved=command.achieved,
            deviation_justification=command.deviation_justification,
            progress=command.progress,
            scope=command.scope,
        )
        if existente is not None:
            # HU-08.03: corregir un seguimiento devuelto no lo regresa a borrador;
            # el motivo del rechazo sigue a la vista hasta que se reenvia.
            item.status = existente.status
            item.review_comment = existente.review_comment
        item = await self.repository.upsert_follow_up(item)
        await _publish(
            self.event_bus,
            actor_id=command.actor.id,
            aggregate_type="poa_form_follow_up",
            aggregate_id=item.id,
            action="upserted",
            data={"form_id": form.id, "quarter": item.quarter},
        )
        return item


class UpdatePoaFollowUpJustification:
    def __init__(self, repository: PoaFormRepository, event_bus: EventBus) -> None:
        self.repository = repository
        self.event_bus = event_bus

    async def execute(
        self,
        command: UpdatePoaFollowUpJustificationCommand,
    ) -> PoaActivityFollowUp:
        if not command.actor.is_planning:
            raise ForbiddenError("Solo Planeación puede editar la justificación.")
        item = await self.repository.get_follow_up(command.follow_up_id)
        if item is None:
            raise ResourceNotFoundError("El seguimiento de la cédula no existe.")
        item.update_justification(command.justification)
        await self.repository.update_follow_up(item)
        await _publish(
            self.event_bus,
            actor_id=command.actor.id,
            aggregate_type="poa_form_follow_up",
            aggregate_id=item.id,
            action="justification_updated",
            data={"quarter": item.quarter},
        )
        return item


def _serialize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serialize(item) for item in value]
    return value


async def _build_snapshot(
    repository: PoaFormRepository,
    evidences: EvidenceRepository,
    detail: PoaFormDetail,
    quarter: int,
) -> dict[str, Any]:
    objectives = {item.number: item for item in await repository.list_objectives()}
    objective = objectives[detail.form.objective_number]
    strategy = await repository.get_strategy(detail.form.strategy_key)
    indicator_catalogs = {
        item.key: item
        for item in await repository.list_indicators(objective_number=detail.form.objective_number)
    }
    activity_catalogs = {
        item.key: item
        for item in await repository.list_activity_catalog(strategy_key=detail.form.strategy_key)
    }
    follow_ups_by_activity: dict[int, list[dict[str, Any]]] = {}
    for follow_up in detail.follow_ups:
        if follow_up.quarter <= quarter:
            linked_evidences = await evidences.list_for(FlowEntity.POA_FORM_FOLLOW_UP, follow_up.id)
            rendered_evidences = []
            for evidence in linked_evidences:
                versions = await evidences.list_versions(evidence.id)
                rendered_evidences.append(
                    {
                        **asdict(evidence),
                        "versiones": [asdict(version) for version in versions],
                    }
                )
            follow_ups_by_activity.setdefault(follow_up.form_activity_id, []).append(
                {**asdict(follow_up), "evidencias": rendered_evidences}
            )

    return _serialize(
        {
            "version_formato": "POA-2026",
            "cuatrimestre": quarter,
            "duracion_cuatrimestres": [asdict(item) for item in detail.quarters],
            "seccion_1_estrategia": {
                "cedula": asdict(detail.form),
                "objetivo": asdict(objective),
                "estrategia": asdict(strategy),
                "area_responsable_id": detail.form.responsible_area_id,
                "alcance_efecto_socioeconomico": (detail.form.scope_and_socioeconomic_effect),
            },
            "seccion_2_indicadores": [
                {
                    **asdict(item),
                    "catalogo": asdict(indicator_catalogs[item.indicator_key]),
                }
                for item in detail.indicators
            ],
            "seccion_3_total_alcanzado": [
                {
                    "cedula_indicador_id": item.id,
                    "indicador_clave": item.indicator_key,
                    "total_alcanzado": item.total_achieved,
                    "porcentaje_alcanzado": item.achieved_percentage,
                }
                for item in detail.indicators
            ],
            "seccion_4_calendarizacion_y_seguimiento": [
                {
                    **asdict(item),
                    "catalogo": asdict(activity_catalogs[item.activity_key]),
                    "seguimientos": follow_ups_by_activity.get(item.id, []),
                }
                for item in detail.activities
            ],
        }
    )


class IssuePoaForm:
    def __init__(
        self,
        repository: PoaFormRepository,
        periods: PeriodRepository,
        exercises: PoaRepository,
        event_bus: EventBus,
        evidences: EvidenceRepository,
    ) -> None:
        self.repository = repository
        self.periods = periods
        self.exercises = exercises
        self.event_bus = event_bus
        self.evidences = evidences

    async def execute(self, command: IssuePoaFormCommand) -> PoaFormIssue:
        ensure_planning(command.actor)
        detail = await self.repository.get_detail(command.form_id)
        if detail is None:
            raise ResourceNotFoundError("La cédula POA no existe.")
        form = detail.form
        await _validate_period(
            repository=self.repository,
            periods=self.periods,
            exercises=self.exercises,
            form=form,
            period_id=command.period_id,
            quarter=command.quarter,
        )
        if not detail.indicators:
            raise ValidationError("La cédula debe incluir al menos un indicador.")
        if not detail.activities:
            raise ValidationError("La cédula debe incluir al menos una actividad.")
        followed_activity_ids = {
            item.form_activity_id for item in detail.follow_ups if item.quarter == command.quarter
        }
        missing = [item.id for item in detail.activities if item.id not in followed_activity_ids]
        if missing:
            raise ValidationError(
                "Todas las actividades deben tener seguimiento del cuatrimestre.",
                details={"actividad_ids": missing},
            )
        incomplete = [
            item.form_activity_id
            for item in detail.follow_ups
            if item.quarter == command.quarter and item.achieved is None
        ]
        if incomplete:
            raise ValidationError(
                "Todos los seguimientos requieren el valor alcanzado para emitir.",
                details={"actividad_ids": incomplete},
            )
        missing_progress_or_scope = [
            item.form_activity_id
            for item in detail.follow_ups
            if item.quarter == command.quarter and (not item.progress or not item.scope)
        ]
        if missing_progress_or_scope:
            raise ValidationError(
                "Todos los seguimientos requieren progreso y alcance para emitir.",
                details={"actividad_ids": missing_progress_or_scope},
            )
        missing_evidence = [
            item.form_activity_id
            for item in detail.follow_ups
            if item.quarter == command.quarter
            and not await _has_file_evidence(self.evidences, item.id)
        ]
        if missing_evidence:
            raise ValidationError(
                "Todos los seguimientos requieren al menos una evidencia para emitir.",
                details={"actividad_ids": missing_evidence},
            )
        if command.quarter == 3 and any(item.total_achieved is None for item in detail.indicators):
            raise ValidationError(
                "Todos los indicadores requieren total alcanzado en el tercer cuatrimestre."
            )
        exercise = await self.exercises.get_exercise(form.exercise_id)
        if exercise is None:
            raise ResourceNotFoundError("El ejercicio POA no existe.")
        issue = PoaFormIssue(
            form_id=form.id,
            quarter=command.quarter,
            period_id=command.period_id,
            name=build_issue_name(form.objective_number, command.quarter, exercise.year),
            snapshot=await _build_snapshot(
                self.repository,
                self.evidences,
                detail,
                command.quarter,
            ),
            issued_by=command.actor.id,
        )
        await self.repository.add_issue(issue)
        await _publish(
            self.event_bus,
            actor_id=command.actor.id,
            aggregate_type="poa_form_issue",
            aggregate_id=issue.id,
            action="issued",
            data={
                "form_id": form.id,
                "quarter": issue.quarter,
                "period_id": issue.period_id,
                "name": issue.name,
            },
        )
        return issue
