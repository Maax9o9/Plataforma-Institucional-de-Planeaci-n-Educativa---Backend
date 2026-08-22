"""Consulta de bitacora; no existe endpoint de modificacion."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request

from app.core.authorization import ensure_area_or_planning
from app.core.schemas import ErrorResponse
from app.core.security import require_roles
from app.shared.domain.exceptions import ResourceNotFoundError

from ..api.schemas import EntradaAuditoriaResponse, PaginaAuditoriaResponse

TAG = "Auditoria"
router = APIRouter(tags=[TAG])


@router.get(
    "/auditoria",
    response_model=list[EntradaAuditoriaResponse],
    summary="Consultar bitacora de acciones",
    description="La bitacora solo expone lectura y se alimenta desde el bus de eventos.",
    responses={403: {"model": ErrorResponse, "description": "Rol insuficiente."}},
)
async def list_audit_entries(
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    usuario_id: int | None = Query(default=None),
    accion: str | None = Query(default=None),
    fecha_desde: datetime | None = Query(default=None),
    fecha_hasta: datetime | None = Query(default=None),
    _current_user=Depends(require_roles("planeacion", "admin_sistema")),
) -> list[EntradaAuditoriaResponse]:
    entries = await request.app.state.audit_repository.list(
        offset=offset,
        limit=limit,
        actor_id=usuario_id,
        action=accion,
        from_date=fecha_desde,
        to_date=fecha_hasta,
    )
    return [EntradaAuditoriaResponse.from_domain(entry) for entry in entries]


@router.get(
    "/bitacora",
    response_model=PaginaAuditoriaResponse,
    summary="Consultar bitacora paginada y filtrable",
)
async def list_log_entries(
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    usuario_id: int | None = Query(default=None),
    accion: str | None = Query(default=None),
    entidad: str | None = Query(default=None),
    entidad_id: int | None = Query(default=None),
    fecha_desde: datetime | None = Query(default=None),
    fecha_hasta: datetime | None = Query(default=None),
    _current_user=Depends(require_roles("planeacion", "admin_sistema")),
) -> PaginaAuditoriaResponse:
    filters = {
        "actor_id": usuario_id,
        "action": accion,
        "from_date": fecha_desde,
        "to_date": fecha_hasta,
        "aggregate_type": entidad,
        "aggregate_id": entidad_id,
    }
    entries = await request.app.state.audit_repository.list(
        offset=offset,
        limit=limit,
        **filters,
    )
    total = await request.app.state.audit_repository.count(**filters)
    return PaginaAuditoriaResponse(
        items=[EntradaAuditoriaResponse.from_domain(entry) for entry in entries],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/indicadores/{indicator_id}/historial",
    response_model=list[EntradaAuditoriaResponse],
    summary="Consultar historial del indicador",
)
async def indicator_history(
    indicator_id: int,
    request: Request,
    current_user=Depends(require_roles("planeacion", "admin_sistema", "responsable_area")),
):
    indicator = await request.app.state.indicator_repository.get_by_id(indicator_id)
    if indicator is None:
        raise ResourceNotFoundError("El indicador no existe.")
    ensure_area_or_planning(current_user, indicator.area_id)
    entries = await request.app.state.audit_repository.list(
        aggregate_type="indicator",
        aggregate_id=indicator_id,
        limit=100,
    )
    return [EntradaAuditoriaResponse.from_domain(entry) for entry in entries]


@router.get(
    "/poa/actividades/{activity_id}/historial",
    summary="Consultar historial de actividad POA",
)
async def poa_activity_history(
    activity_id: int,
    request: Request,
    current_user=Depends(require_roles("planeacion", "admin_sistema", "responsable_area")),
):
    activity = await request.app.state.poa_repository.get_activity(activity_id)
    objective = (
        await request.app.state.poa_repository.get_objective(activity.objective_id)
        if activity
        else None
    )
    process = (
        await request.app.state.poa_repository.get_process(objective.process_id)
        if objective
        else None
    )
    if process is None:
        raise ResourceNotFoundError("La actividad POA no existe.")
    ensure_area_or_planning(current_user, process.area_id)
    entries = await request.app.state.audit_repository.list(
        aggregate_type="poa_activity",
        aggregate_id=activity_id,
        limit=100,
    )
    return [EntradaAuditoriaResponse.from_domain(entry) for entry in entries]
