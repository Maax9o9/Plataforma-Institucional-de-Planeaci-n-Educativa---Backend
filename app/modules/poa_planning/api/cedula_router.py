"""Endpoints alineados con la cédula institucional del POA 2026."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request, status

from app.core.authorization import actor_from_user
from app.core.security import get_current_user, require_roles
from app.shared.domain.exceptions import ForbiddenError, ResourceNotFoundError

from ..application.access_control import can_edit_structure
from ..application.cedula_dto import (
    AddPoaFormActivityCommand,
    AddPoaFormIndicatorCommand,
    CapturePoaIndicatorTotalCommand,
    CreatePoaFormCommand,
    IssuePoaFormCommand,
    PoaQuarterRangeInput,
    RecordPoaFollowUpCommand,
    UpdatePoaFollowUpJustificationCommand,
    UpdatePoaFormActivityCommand,
    UpdatePoaFormCommand,
    UpdatePoaFormIndicatorCommand,
)
from ..application.use_cases.manage_cedula import (
    AddPoaFormActivity,
    AddPoaFormIndicator,
    CapturePoaIndicatorTotal,
    CreatePoaForm,
    IssuePoaForm,
    RecordPoaFollowUp,
    UpdatePoaFollowUpJustification,
    UpdatePoaForm,
    UpdatePoaFormActivity,
    UpdatePoaFormIndicator,
)
from ..domain.cedula_entities import (
    STRATEGY_TYPES,
    PoaActivityFollowUp,
    PoaForm,
    PoaFormActivity,
    PoaFormDetail,
    PoaFormIndicator,
    PoaFormIssue,
    PoaFormQuarter,
    PoaSignatory,
)
from .cedula_dependencies import (
    get_add_form_activity_use_case,
    get_add_form_indicator_use_case,
    get_capture_indicator_total_use_case,
    get_create_form_use_case,
    get_issue_form_use_case,
    get_record_follow_up_use_case,
    get_update_follow_up_justification_use_case,
    get_update_form_activity_use_case,
    get_update_form_indicator_use_case,
    get_update_form_use_case,
)
from .cedula_schemas import (
    ActividadCedulaRespuesta,
    ActividadPoaCatalogoRespuesta,
    ActualizarActividadCedulaRequest,
    ActualizarCedulaPoaRequest,
    ActualizarIndicadorCedulaRequest,
    ActualizarJustificacionSeguimientoRequest,
    AgregarActividadCedulaRequest,
    AgregarIndicadorCedulaRequest,
    CapturarTotalIndicadorRequest,
    CedulaPoaDetalleRespuesta,
    CedulaPoaRespuesta,
    CrearCedulaPoaRequest,
    EmisionCedulaPoaRespuesta,
    EmitirCedulaPoaRequest,
    EstrategiaPoaCatalogoRespuesta,
    IndicadorCedulaRespuesta,
    IndicadorPoaCatalogoRespuesta,
    ObjetivoPoaCatalogoRespuesta,
    RegistrarSeguimientoCedulaRequest,
    SeguimientoCedulaRespuesta,
)

router = APIRouter(prefix="/poa", tags=["Cédulas POA"])
FORM_ROLES = ("planeacion", "planeacion_admin", "admin_sistema", "capturista_poa")
PLANNING_ROLES = ("planeacion", "planeacion_admin", "admin_sistema")
STRUCTURE_ROLES = (*PLANNING_ROLES, "capturista_poa")


def _form_response(
    item: PoaForm, quarters: list[PoaFormQuarter] | tuple = ()
) -> CedulaPoaRespuesta:
    return CedulaPoaRespuesta(
        id=item.id,
        ejercicio_id=item.exercise_id,
        objetivo_numero=item.objective_number,
        estrategia_clave=item.strategy_key,
        area_responsable_id=item.responsible_area_id,
        tipo_estrategia=item.strategy_type,
        firmantes=[{"nombre": s.name, "cargo": s.position} for s in item.signatories],
        alcance_efecto_socioeconomico=item.scope_and_socioeconomic_effect,
        creado_por=item.created_by,
        version=item.version,
        creado_en=item.created_at,
        actualizado_en=item.updated_at,
        cuatrimestres=[
            {
                "numero": quarter.quarter,
                "periodo_id": quarter.period_id,
                "fecha_inicio": quarter.starts_on,
                "fecha_fin": quarter.ends_on,
            }
            for quarter in quarters
        ],
    )


def _percentage(value: Decimal | None, annual_goal: Decimal) -> Decimal | None:
    if value is None or annual_goal == 0:
        return None
    return (value / annual_goal * Decimal(100)).quantize(Decimal("0.01"))


def _indicator_response(item: PoaFormIndicator, catalog) -> IndicadorCedulaRespuesta:
    return IndicadorCedulaRespuesta(
        id=item.id,
        cedula_id=item.form_id,
        indicador_clave=item.indicator_key,
        nombre=catalog.name,
        formula=catalog.formula,
        unidad_medida=catalog.unit,
        meta_institucional=item.institutional_goal,
        linea_base_anio=item.baseline_year,
        linea_base_valor=item.baseline_value,
        porcentaje_actual=item.current_percentage,
        numero_a_lograr=item.target_value,
        porcentaje_a_lograr=item.target_percentage,
        total_alcanzado=item.total_achieved,
        porcentaje_alcanzado=item.achieved_percentage,
    )


def _activity_response(item: PoaFormActivity, catalog) -> ActividadCedulaRespuesta:
    return ActividadCedulaRespuesta(
        id=item.id,
        cedula_id=item.form_id,
        actividad_clave=item.activity_key,
        descripcion=catalog.description,
        unidad_medida=item.unit,
        meta_anual=item.annual_goal,
        area_ejecutora_id=item.executing_area_id,
        observaciones=item.observations,
    )


def _follow_up_response(
    item: PoaActivityFollowUp, annual_goal: Decimal
) -> SeguimientoCedulaRespuesta:
    return SeguimientoCedulaRespuesta(
        id=item.id,
        cedula_actividad_id=item.form_activity_id,
        cuatrimestre=item.quarter,
        periodo_id=item.period_id,
        capturado_por=item.captured_by,
        programado=item.scheduled,
        programado_porcentaje=_percentage(item.scheduled, annual_goal),
        alcanzado=item.achieved,
        alcanzado_porcentaje=_percentage(item.achieved, annual_goal),
        justificacion_desviacion=item.deviation_justification,
        progreso=item.progress,
        alcance=item.scope,
    )


def _issue_response(item: PoaFormIssue) -> EmisionCedulaPoaRespuesta:
    return EmisionCedulaPoaRespuesta(
        id=item.id,
        cedula_id=item.form_id,
        cuatrimestre=item.quarter,
        periodo_id=item.period_id,
        nombre=item.name,
        snapshot=item.snapshot,
        emitido_por=item.issued_by,
        emitido_en=item.issued_at,
    )


async def _ensure_access(repository, item: PoaForm, current_user, areas) -> None:
    if await can_edit_structure(actor_from_user(current_user), areas):
        return
    if current_user.area_id is None or not current_user.has_any_role({"capturista_poa"}):
        raise ForbiddenError("La consulta requiere un capturista con área asignada.")
    detail = await repository.get_detail(item.id)
    assigned = detail is not None and any(
        activity.executing_area_id == current_user.area_id for activity in detail.activities
    )
    if current_user.area_id != item.responsible_area_id and not assigned:
        raise ForbiddenError("La cédula POA no tiene actividades asignadas al área del usuario.")


async def _detail_response(
    repository, detail: PoaFormDetail, exercises
) -> CedulaPoaDetalleRespuesta:
    objectives = {item.number: item for item in await repository.list_objectives()}
    strategy = await repository.get_strategy(detail.form.strategy_key)
    indicator_catalogs = {
        item.key: item
        for item in await repository.list_indicators(objective_number=detail.form.objective_number)
    }
    activity_catalogs = {
        item.key: item
        for item in await repository.list_activity_catalog(strategy_key=detail.form.strategy_key)
    }
    activities_by_id = {item.id: item for item in detail.activities}
    form_data = _form_response(detail.form, detail.quarters).model_dump()
    exercise = await exercises.get_exercise(detail.form.exercise_id)
    return CedulaPoaDetalleRespuesta(
        **form_data,
        anio=exercise.year,
        titulo=f"PROGRAMA OPERATIVO ANUAL {exercise.year}",
        institucion="UNIVERSIDAD POLITÉCNICA DE CHIAPAS",
        formato='FORMATO 01 "DESARROLLO DE PROCESOS"',
        estrategia_numero=int(detail.form.strategy_key.split(".")[-1]),
        objetivo_denominacion=objectives[detail.form.objective_number].denomination,
        estrategia_denominacion=strategy.denomination,
        indicadores=[
            _indicator_response(item, indicator_catalogs[item.indicator_key])
            for item in detail.indicators
        ],
        actividades=[
            _activity_response(item, activity_catalogs[item.activity_key])
            for item in detail.activities
        ],
        seguimientos=[
            _follow_up_response(
                item,
                activities_by_id[item.form_activity_id].annual_goal,
            )
            for item in detail.follow_ups
        ],
    )


@router.get("/catalogos/tipos-estrategia", response_model=list[str])
async def list_strategy_types(_user=Depends(get_current_user)):
    return list(STRATEGY_TYPES)


@router.get(
    "/catalogos/objetivos",
    response_model=list[ObjetivoPoaCatalogoRespuesta],
    summary="Consultar objetivos del formato POA",
)
async def list_objectives(request: Request, _user=Depends(get_current_user)):
    items = await request.app.state.poa_form_repository.list_objectives()
    return [
        ObjetivoPoaCatalogoRespuesta(
            clave=item.key,
            numero=item.number,
            denominacion=item.denomination,
            activo=item.is_active,
        )
        for item in items
    ]


@router.get(
    "/catalogos/estrategias",
    response_model=list[EstrategiaPoaCatalogoRespuesta],
    summary="Consultar denominaciones de estrategia",
)
async def list_strategies(
    request: Request,
    objetivo_numero: int | None = Query(default=None, ge=1, le=6),
    _user=Depends(get_current_user),
):
    items = await request.app.state.poa_form_repository.list_strategies(
        objective_number=objetivo_numero
    )
    return [
        EstrategiaPoaCatalogoRespuesta(
            clave=item.key,
            objetivo_numero=item.objective_number,
            denominacion=item.denomination,
            activo=item.is_active,
        )
        for item in items
    ]


@router.get(
    "/catalogos/indicadores",
    response_model=list[IndicadorPoaCatalogoRespuesta],
    summary="Consultar indicadores, fórmulas y unidades predefinidas",
)
async def list_indicators(
    request: Request,
    objetivo_numero: int | None = Query(default=None, ge=1, le=6),
    _user=Depends(get_current_user),
):
    items = await request.app.state.poa_form_repository.list_indicators(
        objective_number=objetivo_numero
    )
    return [
        IndicadorPoaCatalogoRespuesta(
            clave=item.key,
            objetivo_numero=item.objective_number,
            nombre=item.name,
            formula=item.formula,
            unidad_medida=item.unit,
            activo=item.is_active,
        )
        for item in items
    ]


@router.get(
    "/catalogos/actividades",
    response_model=list[ActividadPoaCatalogoRespuesta],
    summary="Consultar actividades predefinidas por estrategia",
)
async def list_activity_catalog(
    request: Request,
    estrategia_clave: str | None = None,
    _user=Depends(get_current_user),
):
    items = await request.app.state.poa_form_repository.list_activity_catalog(
        strategy_key=estrategia_clave
    )
    return [
        ActividadPoaCatalogoRespuesta(
            clave=item.key,
            estrategia_clave=item.strategy_key,
            descripcion=item.description,
            activo=item.is_active,
        )
        for item in items
    ]


@router.post(
    "/cedulas",
    response_model=CedulaPoaRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Crear la estructura anual de una cédula POA",
)
async def create_form(
    body: CrearCedulaPoaRequest,
    request: Request,
    current_user=Depends(require_roles(*PLANNING_ROLES)),
    use_case: CreatePoaForm = Depends(get_create_form_use_case),
):
    item = await use_case.execute(
        CreatePoaFormCommand(
            exercise_id=body.ejercicio_id,
            strategy_key=body.estrategia_clave,
            responsible_area_id=body.area_responsable_id,
            scope_and_socioeconomic_effect=body.alcance_efecto_socioeconomico,
            strategy_type=body.tipo_estrategia,
            signatories=tuple(
                PoaSignatory(name=s.nombre, position=s.cargo) for s in body.firmantes
            ),
            quarters=tuple(
                PoaQuarterRangeInput(
                    quarter=item.numero,
                    starts_on=item.fecha_inicio,
                    ends_on=item.fecha_fin,
                )
                for item in body.cuatrimestres
            ),
            actor=actor_from_user(current_user),
        )
    )
    quarters = await request.app.state.poa_form_repository.list_form_quarters(item.id)
    return _form_response(item, quarters)


@router.get(
    "/cedulas",
    response_model=list[CedulaPoaRespuesta],
    summary="Consultar cédulas POA",
)
async def list_forms(
    request: Request,
    ejercicio_id: int | None = None,
    objetivo_numero: int | None = Query(default=None, ge=1, le=6),
    area_responsable_id: int | None = None,
    current_user=Depends(require_roles(*FORM_ROLES)),
):
    items = await request.app.state.poa_form_repository.list_forms(
        exercise_id=ejercicio_id,
        objective_number=objetivo_numero,
        responsible_area_id=area_responsable_id,
    )
    if not current_user.has_any_role({"planeacion", "planeacion_admin", "admin_sistema"}):
        visible = []
        for item in items:
            try:
                await _ensure_access(
                    request.app.state.poa_form_repository,
                    item,
                    current_user,
                    request.app.state.area_repository,
                )
                visible.append(item)
            except ForbiddenError:
                continue
        items = visible
    return [
        _form_response(
            item,
            await request.app.state.poa_form_repository.list_form_quarters(item.id),
        )
        for item in items
    ]


@router.get(
    "/emisiones/{issue_id}",
    response_model=EmisionCedulaPoaRespuesta,
    summary="Consultar el respaldo inmutable de una cédula",
)
async def get_issue(
    issue_id: int,
    request: Request,
    current_user=Depends(require_roles(*FORM_ROLES)),
):
    item = await request.app.state.poa_form_repository.get_issue(issue_id)
    if item is None:
        raise ResourceNotFoundError("La emisión de la cédula no existe.")
    form = await request.app.state.poa_form_repository.get_form(item.form_id)
    if form is None:
        raise ResourceNotFoundError("La cédula POA no existe.")
    await _ensure_access(
        request.app.state.poa_form_repository,
        form,
        current_user,
        request.app.state.area_repository,
    )
    return _issue_response(item)


@router.get(
    "/cedulas/{form_id}",
    response_model=CedulaPoaDetalleRespuesta,
    summary="Consultar las cuatro secciones de una cédula POA",
)
async def get_form_detail(
    form_id: int,
    request: Request,
    current_user=Depends(require_roles(*FORM_ROLES)),
):
    detail = await request.app.state.poa_form_repository.get_detail(form_id)
    if detail is None:
        raise ResourceNotFoundError("La cédula POA no existe.")
    await _ensure_access(
        request.app.state.poa_form_repository,
        detail.form,
        current_user,
        request.app.state.area_repository,
    )
    return await _detail_response(
        request.app.state.poa_form_repository, detail, request.app.state.poa_repository
    )


@router.patch(
    "/cedulas/{form_id}",
    response_model=CedulaPoaRespuesta,
    summary="Actualizar la sección de estrategia de la cédula",
)
async def update_form(
    form_id: int,
    body: ActualizarCedulaPoaRequest,
    request: Request,
    current_user=Depends(require_roles(*STRUCTURE_ROLES)),
    use_case: UpdatePoaForm = Depends(get_update_form_use_case),
):
    item = await use_case.execute(
        UpdatePoaFormCommand(
            form_id=form_id,
            strategy_key=body.estrategia_clave,
            responsible_area_id=body.area_responsable_id,
            scope_and_socioeconomic_effect=body.alcance_efecto_socioeconomico,
            strategy_type=body.tipo_estrategia,
            signatories=(
                tuple(PoaSignatory(name=s.nombre, position=s.cargo) for s in body.firmantes)
                if body.firmantes is not None
                else None
            ),
            actor=actor_from_user(current_user),
        )
    )
    quarters = await request.app.state.poa_form_repository.list_form_quarters(item.id)
    return _form_response(item, quarters)


@router.post(
    "/cedulas/{form_id}/indicadores",
    response_model=IndicadorCedulaRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Agregar un indicador predefinido a la cédula",
)
async def add_form_indicator(
    form_id: int,
    body: AgregarIndicadorCedulaRequest,
    request: Request,
    current_user=Depends(require_roles(*STRUCTURE_ROLES)),
    use_case: AddPoaFormIndicator = Depends(get_add_form_indicator_use_case),
):
    item = await use_case.execute(
        AddPoaFormIndicatorCommand(
            form_id=form_id,
            indicator_key=body.indicador_clave,
            institutional_goal=body.meta_institucional,
            baseline_year=body.linea_base_anio,
            baseline_value=body.linea_base_valor,
            current_percentage=body.porcentaje_actual,
            target_value=body.numero_a_lograr,
            target_percentage=body.porcentaje_a_lograr,
            actor=actor_from_user(current_user),
        )
    )
    catalog = await request.app.state.poa_form_repository.get_indicator(item.indicator_key)
    return _indicator_response(item, catalog)


@router.patch(
    "/cedulas/indicadores/{form_indicator_id}",
    response_model=IndicadorCedulaRespuesta,
    summary="Actualizar los datos capturables de un indicador de la cédula",
)
async def update_form_indicator(
    form_indicator_id: int,
    body: ActualizarIndicadorCedulaRequest,
    request: Request,
    current_user=Depends(require_roles(*STRUCTURE_ROLES)),
    use_case: UpdatePoaFormIndicator = Depends(get_update_form_indicator_use_case),
):
    item = await use_case.execute(
        UpdatePoaFormIndicatorCommand(
            form_indicator_id=form_indicator_id,
            institutional_goal=body.meta_institucional,
            baseline_year=body.linea_base_anio,
            baseline_value=body.linea_base_valor,
            current_percentage=body.porcentaje_actual,
            target_value=body.numero_a_lograr,
            target_percentage=body.porcentaje_a_lograr,
            actor=actor_from_user(current_user),
        )
    )
    catalog = await request.app.state.poa_form_repository.get_indicator(item.indicator_key)
    return _indicator_response(item, catalog)


@router.patch(
    "/cedulas/indicadores/{form_indicator_id}/total-alcanzado",
    response_model=IndicadorCedulaRespuesta,
    summary="Capturar el total alcanzado durante el tercer cuatrimestre",
)
async def capture_indicator_total(
    form_indicator_id: int,
    body: CapturarTotalIndicadorRequest,
    request: Request,
    current_user=Depends(require_roles(*STRUCTURE_ROLES)),
    use_case: CapturePoaIndicatorTotal = Depends(get_capture_indicator_total_use_case),
):
    item = await use_case.execute(
        CapturePoaIndicatorTotalCommand(
            form_indicator_id=form_indicator_id,
            period_id=body.periodo_id,
            total_achieved=body.total_alcanzado,
            achieved_percentage=body.porcentaje_alcanzado,
            actor=actor_from_user(current_user),
        )
    )
    catalog = await request.app.state.poa_form_repository.get_indicator(item.indicator_key)
    return _indicator_response(item, catalog)


@router.post(
    "/cedulas/{form_id}/actividades",
    response_model=ActividadCedulaRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Agregar una actividad predefinida a la cédula",
)
async def add_form_activity(
    form_id: int,
    body: AgregarActividadCedulaRequest,
    request: Request,
    current_user=Depends(require_roles(*STRUCTURE_ROLES)),
    use_case: AddPoaFormActivity = Depends(get_add_form_activity_use_case),
):
    item = await use_case.execute(
        AddPoaFormActivityCommand(
            form_id=form_id,
            activity_key=body.actividad_clave,
            unit=body.unidad_medida,
            annual_goal=body.meta_anual,
            executing_area_id=body.area_ejecutora_id,
            observations=body.observaciones,
            actor=actor_from_user(current_user),
        )
    )
    catalog = await request.app.state.poa_form_repository.get_activity_catalog(item.activity_key)
    return _activity_response(item, catalog)


@router.patch(
    "/cedulas/actividades/{form_activity_id}",
    response_model=ActividadCedulaRespuesta,
    summary="Actualizar los datos configurables de una actividad",
)
async def update_form_activity(
    form_activity_id: int,
    body: ActualizarActividadCedulaRequest,
    request: Request,
    current_user=Depends(require_roles(*STRUCTURE_ROLES)),
    use_case: UpdatePoaFormActivity = Depends(get_update_form_activity_use_case),
):
    item = await use_case.execute(
        UpdatePoaFormActivityCommand(
            form_activity_id=form_activity_id,
            unit=body.unidad_medida,
            annual_goal=body.meta_anual,
            executing_area_id=body.area_ejecutora_id,
            observations=body.observaciones,
            actor=actor_from_user(current_user),
        )
    )
    catalog = await request.app.state.poa_form_repository.get_activity_catalog(item.activity_key)
    return _activity_response(item, catalog)


@router.put(
    "/cedulas/actividades/{form_activity_id}/seguimientos/{quarter}",
    response_model=SeguimientoCedulaRespuesta,
    summary="Registrar programación y avance cuatrimestral de una actividad",
)
async def record_follow_up(
    form_activity_id: int,
    quarter: int,
    body: RegistrarSeguimientoCedulaRequest,
    request: Request,
    current_user=Depends(require_roles(*FORM_ROLES)),
    use_case: RecordPoaFollowUp = Depends(get_record_follow_up_use_case),
):
    item = await use_case.execute(
        RecordPoaFollowUpCommand(
            form_activity_id=form_activity_id,
            quarter=quarter,
            period_id=body.periodo_id,
            scheduled=body.programado,
            achieved=body.alcanzado,
            deviation_justification=body.justificacion_desviacion,
            progress=body.progreso,
            scope=body.alcance,
            actor=actor_from_user(current_user),
        )
    )
    activity = await request.app.state.poa_form_repository.get_form_activity(form_activity_id)
    return _follow_up_response(item, activity.annual_goal)


@router.patch(
    "/cedulas/seguimientos/{follow_up_id}/justificacion",
    response_model=SeguimientoCedulaRespuesta,
    summary="Mejorar únicamente la justificación de desviaciones",
)
async def update_follow_up_justification(
    follow_up_id: int,
    body: ActualizarJustificacionSeguimientoRequest,
    request: Request,
    current_user=Depends(require_roles(*PLANNING_ROLES)),
    use_case: UpdatePoaFollowUpJustification = Depends(get_update_follow_up_justification_use_case),
):
    item = await use_case.execute(
        UpdatePoaFollowUpJustificationCommand(
            follow_up_id=follow_up_id,
            justification=body.justificacion_desviacion,
            actor=actor_from_user(current_user),
        )
    )
    activity = await request.app.state.poa_form_repository.get_form_activity(item.form_activity_id)
    return _follow_up_response(item, activity.annual_goal)


@router.post(
    "/cedulas/{form_id}/emisiones",
    response_model=EmisionCedulaPoaRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Emitir y respaldar la cédula del cuatrimestre",
)
async def issue_form(
    form_id: int,
    body: EmitirCedulaPoaRequest,
    current_user=Depends(require_roles(*PLANNING_ROLES)),
    use_case: IssuePoaForm = Depends(get_issue_form_use_case),
):
    item = await use_case.execute(
        IssuePoaFormCommand(
            form_id=form_id,
            quarter=body.cuatrimestre,
            period_id=body.periodo_id,
            actor=actor_from_user(current_user),
        )
    )
    return _issue_response(item)


@router.get(
    "/cedulas/{form_id}/emisiones",
    response_model=list[EmisionCedulaPoaRespuesta],
    summary="Consultar respaldos cuatrimestrales de la cédula",
)
async def list_form_issues(
    form_id: int,
    request: Request,
    current_user=Depends(require_roles(*FORM_ROLES)),
):
    form = await request.app.state.poa_form_repository.get_form(form_id)
    if form is None:
        raise ResourceNotFoundError("La cédula POA no existe.")
    await _ensure_access(
        request.app.state.poa_form_repository,
        form,
        current_user,
        request.app.state.area_repository,
    )
    items = await request.app.state.poa_form_repository.list_issues(form_id)
    return [_issue_response(item) for item in items]
