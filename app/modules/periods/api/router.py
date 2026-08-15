"""Endpoints para el ciclo de vida de periodos."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status

from app.core.schemas import ErrorResponse
from app.core.security import get_current_user, require_roles

from ..application.dto import ChangePeriodCommand, CreatePeriodCommand, ReopenPeriodCommand
from ..application.use_cases.change_period_status import ClosePeriod, OpenPeriod
from ..application.use_cases.create_period import CreatePeriod
from ..application.use_cases.reopen_period import ReopenPeriod
from .dependencies import (
    get_close_period_use_case,
    get_create_period_use_case,
    get_open_period_use_case,
    get_reopen_period_use_case,
)
from .schemas import CrearPeriodoRequest, PeriodoResponse, ReabrirPeriodoRequest

TAG = "Periodos"
router = APIRouter(prefix="/periodos", tags=[TAG])
MANAGE_ROLES = ("planeacion", "admin_sistema")


@router.get(
    "",
    response_model=list[PeriodoResponse],
    summary="Consultar periodos de captura",
    responses={401: {"model": ErrorResponse, "description": "Autenticacion requerida."}},
)
async def list_periods(
    request: Request,
    user=Depends(get_current_user),
) -> list[PeriodoResponse]:
    del user
    periods = await request.app.state.period_repository.list()
    return [PeriodoResponse.from_domain(period) for period in periods]


@router.post(
    "",
    response_model=PeriodoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear periodo de captura",
    responses={
        403: {"model": ErrorResponse, "description": "Rol insuficiente."},
        409: {"model": ErrorResponse, "description": "Las fechas se traslapan."},
    },
)
async def create_period(
    body: CrearPeriodoRequest,
    current_user=Depends(require_roles(*MANAGE_ROLES)),
    use_case: CreatePeriod = Depends(get_create_period_use_case),
) -> PeriodoResponse:
    period = await use_case.execute(
        CreatePeriodCommand(
            name=body.etiqueta,
            starts_on=body.fecha_inicio,
            ends_on=body.fecha_limite,
            period_type=body.tipo,
            periodicity=body.periodicidad,
            year=body.anio,
            actor_id=current_user.id,
        )
    )
    return PeriodoResponse.from_domain(period)


@router.post(
    "/{period_id}/abrir",
    response_model=PeriodoResponse,
    summary="Abrir periodo de captura",
    responses={
        403: {"model": ErrorResponse, "description": "Rol insuficiente."},
        404: {"model": ErrorResponse, "description": "Periodo inexistente."},
        422: {"model": ErrorResponse, "description": "Transicion no permitida."},
    },
)
async def open_period(
    period_id: int,
    current_user=Depends(require_roles(*MANAGE_ROLES)),
    use_case: OpenPeriod = Depends(get_open_period_use_case),
) -> PeriodoResponse:
    period = await use_case.execute(
        ChangePeriodCommand(period_id=period_id, actor_id=current_user.id)
    )
    return PeriodoResponse.from_domain(period)


@router.post(
    "/{period_id}/cerrar",
    response_model=PeriodoResponse,
    summary="Cerrar periodo de captura",
    responses={
        403: {"model": ErrorResponse, "description": "Rol insuficiente."},
        404: {"model": ErrorResponse, "description": "Periodo inexistente."},
        422: {"model": ErrorResponse, "description": "Transicion no permitida."},
    },
)
async def close_period(
    period_id: int,
    current_user=Depends(require_roles(*MANAGE_ROLES)),
    use_case: ClosePeriod = Depends(get_close_period_use_case),
) -> PeriodoResponse:
    period = await use_case.execute(
        ChangePeriodCommand(period_id=period_id, actor_id=current_user.id)
    )
    return PeriodoResponse.from_domain(period)


@router.post(
    "/{period_id}/reabrir",
    response_model=PeriodoResponse,
    summary="Reabrir periodo con motivo obligatorio",
    responses={
        403: {"model": ErrorResponse, "description": "Rol insuficiente."},
        404: {"model": ErrorResponse, "description": "Periodo inexistente."},
        422: {"model": ErrorResponse, "description": "Motivo o transicion invalidos."},
    },
)
async def reopen_period(
    period_id: int,
    body: ReabrirPeriodoRequest,
    current_user=Depends(require_roles(*MANAGE_ROLES)),
    use_case: ReopenPeriod = Depends(get_reopen_period_use_case),
) -> PeriodoResponse:
    period = await use_case.execute(
        ReopenPeriodCommand(
            period_id=period_id,
            reason=body.motivo,
            actor_id=current_user.id,
        )
    )
    return PeriodoResponse.from_domain(period)
