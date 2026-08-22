"""Endpoints del catalogo maestro de indicadores."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request, status

from app.core.schemas import ErrorResponse
from app.core.security import get_current_user, require_roles
from app.shared.domain.exceptions import ResourceNotFoundError

from ..application.dto import (
    ChangeIndicatorStatusCommand,
    ChangePeriodicityCommand,
    CreateBaselineCommand,
    CreateGoalCommand,
    RegisterIndicatorCommand,
    UpdateIndicatorCommand,
)
from ..application.use_cases.manage_indicator import (
    ChangeIndicatorPeriodicity,
    CreateBaseline,
    CreateGoal,
    DeactivateIndicator,
    UpdateIndicator,
)
from ..application.use_cases.register_indicator import RegisterIndicator
from .dependencies import (
    get_change_periodicity_use_case,
    get_create_baseline_use_case,
    get_create_goal_use_case,
    get_deactivate_indicator_use_case,
    get_register_indicator_use_case,
    get_update_indicator_use_case,
)
from .schemas import (
    ActualizarIndicadorRequest,
    AsociarCriteriosRequest,
    CambiarPeriodicidadRequest,
    CoberturaSeaesRespuesta,
    CriterioCoberturaRespuesta,
    IndicadorDetalleRespuesta,
    IndicadorRespuesta,
    LineaBaseRequest,
    LineaBaseRespuesta,
    MetaIndicadorRequest,
    MetaIndicadorRespuesta,
    PaginaIndicadoresRespuesta,
    RegistrarIndicadorRequest,
)

TAG = "Indicadores"
router = APIRouter(prefix="/indicadores", tags=[TAG])
MANAGE_ROLES = ("planeacion", "admin_sistema")


@router.get(
    "",
    response_model=PaginaIndicadoresRespuesta,
    summary="Consultar indicadores (F1.1)",
    responses={401: {"model": ErrorResponse, "description": "Autenticacion requerida."}},
)
async def list_indicators(
    request: Request,
    activos: bool = Query(default=True),
    q: str | None = Query(default=None),
    area_id: int | None = Query(default=None),
    responsable_id: int | None = Query(default=None),
    instrumento_id: int | None = Query(default=None),
    criterio_seaes_id: int | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    _current_user=Depends(get_current_user),
) -> PaginaIndicadoresRespuesta:
    indicators = await request.app.state.indicator_repository.list(
        active_only=activos,
    )
    if q:
        normalized = q.strip().casefold()
        indicators = [
            item
            for item in indicators
            if normalized in item.key.casefold() or normalized in item.name.casefold()
        ]
    if area_id is not None:
        indicators = [item for item in indicators if item.area_id == area_id]
    if responsable_id is not None:
        indicators = [item for item in indicators if item.responsible_id == responsable_id]
    if instrumento_id is not None:
        indicators = [item for item in indicators if instrumento_id in item.instrument_ids]
    if criterio_seaes_id is not None:
        indicators = [item for item in indicators if criterio_seaes_id in item.criteria_ids]
    total = len(indicators)
    return PaginaIndicadoresRespuesta(
        items=[
            IndicadorRespuesta.from_domain(item) for item in indicators[offset : offset + limit]
        ],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/cobertura-seaes",
    response_model=CoberturaSeaesRespuesta,
    summary="Consultar cobertura de criterios SEAES",
)
async def seaes_coverage(
    request: Request,
    _current_user=Depends(get_current_user),
) -> CoberturaSeaesRespuesta:
    criteria = await request.app.state.criteria_repository.list()
    indicators = await request.app.state.indicator_repository.list(active_only=True)
    rows = []
    for criterion in criteria:
        count = sum(criterion.id in indicator.criteria_ids for indicator in indicators)
        rows.append(
            CriterioCoberturaRespuesta(
                id=criterion.id,
                clave=criterion.key,
                nombre=criterion.name,
                indicadores_asociados=count,
                cubierto=count > 0,
            )
        )
    covered = sum(row.cubierto for row in rows)
    percentage = (
        (Decimal(covered) * Decimal(100) / Decimal(len(rows))).quantize(Decimal("0.01"))
        if rows
        else Decimal("0.00")
    )
    return CoberturaSeaesRespuesta(
        total_criterios=len(rows),
        criterios_cubiertos=covered,
        porcentaje_cobertura=percentage,
        criterios=rows,
    )


@router.get(
    "/{indicator_id}",
    response_model=IndicadorDetalleRespuesta,
    summary="Consultar detalle integral del indicador",
)
async def get_indicator(
    indicator_id: int,
    request: Request,
    _current_user=Depends(get_current_user),
) -> IndicadorDetalleRespuesta:
    indicator = await request.app.state.indicator_repository.get_by_id(indicator_id)
    if indicator is None:
        raise ResourceNotFoundError("El indicador no existe.")
    baseline = await request.app.state.indicator_repository.get_baseline(indicator_id)
    goals = await request.app.state.indicator_repository.list_goals(indicator_id)
    return IndicadorDetalleRespuesta(
        **IndicadorRespuesta.from_domain(indicator).model_dump(),
        linea_base=LineaBaseRespuesta.from_domain(baseline) if baseline else None,
        metas=[MetaIndicadorRespuesta.from_domain(goal) for goal in goals],
    )


@router.get(
    "/{indicator_id}/linea-base",
    response_model=LineaBaseRespuesta,
    summary="Consultar linea base del indicador",
)
async def get_baseline(indicator_id: int, request: Request, _user=Depends(get_current_user)):
    baseline = await request.app.state.indicator_repository.get_baseline(indicator_id)
    if baseline is None:
        raise ResourceNotFoundError("El indicador no tiene linea base.")
    return LineaBaseRespuesta.from_domain(baseline)


@router.get(
    "/{indicator_id}/metas",
    response_model=list[MetaIndicadorRespuesta],
    summary="Consultar metas del indicador",
)
async def get_goals(indicator_id: int, request: Request, _user=Depends(get_current_user)):
    if await request.app.state.indicator_repository.get_by_id(indicator_id) is None:
        raise ResourceNotFoundError("El indicador no existe.")
    goals = await request.app.state.indicator_repository.list_goals(indicator_id)
    return [MetaIndicadorRespuesta.from_domain(goal) for goal in goals]


@router.get(
    "/{indicator_id}/criterios-seaes",
    response_model=list[int],
    summary="Consultar criterios SEAES asociados",
)
async def get_indicator_criteria(
    indicator_id: int, request: Request, _user=Depends(get_current_user)
) -> list[int]:
    indicator = await request.app.state.indicator_repository.get_by_id(indicator_id)
    if indicator is None:
        raise ResourceNotFoundError("El indicador no existe.")
    return sorted(indicator.criteria_ids)


@router.put(
    "/{indicator_id}/criterios-seaes",
    response_model=list[int],
    summary="Reemplazar criterios SEAES asociados",
)
async def set_indicator_criteria(
    indicator_id: int,
    body: AsociarCriteriosRequest,
    request: Request,
    _current_user=Depends(require_roles(*MANAGE_ROLES)),
) -> list[int]:
    indicator = await request.app.state.indicator_repository.get_by_id(indicator_id)
    if indicator is None:
        raise ResourceNotFoundError("El indicador no existe.")
    known = {item.id for item in await request.app.state.criteria_repository.list()}
    missing = body.criterio_ids - known
    if missing:
        raise ResourceNotFoundError("Uno o mas criterios SEAES no existen.", sorted(missing))
    await request.app.state.indicator_repository.set_criteria(indicator_id, body.criterio_ids)
    return sorted(body.criterio_ids)


@router.post(
    "",
    response_model=IndicadorRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar indicador",
    responses={
        403: {"model": ErrorResponse, "description": "Rol insuficiente."},
        409: {"model": ErrorResponse, "description": "Clave duplicada."},
        422: {"model": ErrorResponse, "description": "Clasificacion o datos invalidos."},
    },
)
async def create_indicator(
    body: RegistrarIndicadorRequest,
    current_user=Depends(require_roles(*MANAGE_ROLES)),
    use_case: RegisterIndicator = Depends(get_register_indicator_use_case),
) -> IndicadorRespuesta:
    indicator = await use_case.execute(
        RegisterIndicatorCommand(
            key=body.clave,
            name=body.nombre,
            calculation_method=body.metodo_calculo,
            unit=body.unidad_medida,
            area_id=body.area_id,
            responsible_id=body.responsable_id,
            periodicity=body.periodicidad,
            definition=body.definicion,
            dimension=body.dimension,
            verification_document=body.documento_verificacion,
            information_source=body.fuente_informacion,
            methodological_notes=body.observaciones_metodologicas,
            indicator_type_id=body.tipo_indicador_id,
            instrument_ids=body.instrumento_ids,
            green_threshold=body.umbral_verde_min,
            yellow_threshold=body.umbral_amarillo_min,
            actor_id=current_user.id,
        )
    )
    return IndicadorRespuesta.from_domain(indicator)


@router.patch(
    "/{indicator_id}",
    response_model=IndicadorRespuesta,
    summary="Editar indicador",
    responses={
        403: {"model": ErrorResponse, "description": "Rol insuficiente."},
        404: {"model": ErrorResponse, "description": "Indicador inexistente."},
        409: {"model": ErrorResponse, "description": "Clave duplicada."},
    },
)
async def update_indicator(
    indicator_id: int,
    body: ActualizarIndicadorRequest,
    current_user=Depends(require_roles(*MANAGE_ROLES)),
    use_case: UpdateIndicator = Depends(get_update_indicator_use_case),
) -> IndicadorRespuesta:
    changes = body.model_dump(exclude_none=True)
    expected_version = changes.pop("version", None)
    changes = {
        "name": changes.pop("nombre", None),
        "calculation_method": changes.pop("metodo_calculo", None),
        "unit": changes.pop("unidad_medida", None),
        "definition": changes.pop("definicion", None),
        "dimension": changes.pop("dimension", None),
        "verification_document": changes.pop("documento_verificacion", None),
        "information_source": changes.pop("fuente_informacion", None),
        "methodological_notes": changes.pop("observaciones_metodologicas", None),
        "area_id": changes.pop("area_id", None),
        "responsible_id": changes.pop("responsable_id", None),
        "indicator_type_id": changes.pop("tipo_indicador_id", None),
    }
    changes = {key: value for key, value in changes.items() if value is not None}
    indicator = await use_case.execute(
        UpdateIndicatorCommand(
            indicator_id=indicator_id,
            actor_id=current_user.id,
            changes=changes,
            expected_version=expected_version,
        )
    )
    return IndicadorRespuesta.from_domain(indicator)


@router.post(
    "/{indicator_id}/desactivar",
    response_model=IndicadorRespuesta,
    summary="Desactivar indicador",
    responses={403: {"model": ErrorResponse, "description": "Rol insuficiente."}},
)
async def deactivate_indicator(
    indicator_id: int,
    current_user=Depends(require_roles(*MANAGE_ROLES)),
    use_case: DeactivateIndicator = Depends(get_deactivate_indicator_use_case),
) -> IndicadorRespuesta:
    indicator = await use_case.execute(
        ChangeIndicatorStatusCommand(indicator_id=indicator_id, actor_id=current_user.id)
    )
    return IndicadorRespuesta.from_domain(indicator)


@router.post(
    "/{indicator_id}/linea-base",
    response_model=LineaBaseRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar linea base",
    responses={409: {"model": ErrorResponse, "description": "La linea base ya existe."}},
)
async def create_baseline(
    indicator_id: int,
    body: LineaBaseRequest,
    current_user=Depends(require_roles(*MANAGE_ROLES)),
    use_case: CreateBaseline = Depends(get_create_baseline_use_case),
) -> LineaBaseRespuesta:
    baseline = await use_case.execute(
        CreateBaselineCommand(
            indicator_id=indicator_id,
            year=body.anio,
            period=body.periodo,
            value=body.valor,
            actor_id=current_user.id,
        )
    )
    return LineaBaseRespuesta.from_domain(baseline)


@router.post(
    "/{indicator_id}/metas",
    response_model=MetaIndicadorRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar meta por periodo",
    responses={409: {"model": ErrorResponse, "description": "La meta ya existe."}},
)
async def create_goal(
    indicator_id: int,
    body: MetaIndicadorRequest,
    current_user=Depends(require_roles(*MANAGE_ROLES)),
    use_case: CreateGoal = Depends(get_create_goal_use_case),
) -> MetaIndicadorRespuesta:
    goal = await use_case.execute(
        CreateGoalCommand(
            indicator_id=indicator_id,
            period_id=body.periodo_id,
            value=body.valor,
            actor_id=current_user.id,
        )
    )
    return MetaIndicadorRespuesta.from_domain(goal)


@router.patch(
    "/{indicator_id}/periodicidad",
    response_model=IndicadorRespuesta,
    summary="Cambiar periodicidad del indicador",
)
async def change_periodicity(
    indicator_id: int,
    body: CambiarPeriodicidadRequest,
    current_user=Depends(require_roles(*MANAGE_ROLES)),
    use_case: ChangeIndicatorPeriodicity = Depends(get_change_periodicity_use_case),
) -> IndicadorRespuesta:
    indicator = await use_case.execute(
        ChangePeriodicityCommand(
            indicator_id=indicator_id,
            periodicity=body.periodicidad,
            actor_id=current_user.id,
        )
    )
    return IndicadorRespuesta.from_domain(indicator)
