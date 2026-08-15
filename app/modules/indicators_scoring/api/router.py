"""Endpoints de evaluacion y semaforizacion."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.core.schemas import ErrorResponse
from app.core.security import get_current_user, require_roles

from ..application.dto import UpdateThresholdsCommand
from ..application.use_cases.update_thresholds import (
    UpdateGlobalThresholds,
    UpdateIndicatorThresholds,
)
from .dependencies import (
    get_update_global_thresholds_use_case,
    get_update_indicator_thresholds_use_case,
)
from .schemas import (
    TendenciaPuntoRespuesta,
    UmbralesPersonalizadosRequest,
    UmbralesSemaforoRequest,
    UmbralesSemaforoRespuesta,
)

TAG = "Evaluacion de indicadores"
router = APIRouter(tags=[TAG])


@router.get(
    "/config/semaforos",
    response_model=UmbralesSemaforoRespuesta,
    summary="Consultar umbrales globales de semaforizacion",
)
async def get_global_thresholds(
    request: Request,
    _current_user=Depends(get_current_user),
) -> UmbralesSemaforoRespuesta:
    thresholds = await request.app.state.threshold_config_repository.get()
    return UmbralesSemaforoRespuesta.from_domain(thresholds)


@router.patch(
    "/config/semaforos",
    response_model=UmbralesSemaforoRespuesta,
    summary="Actualizar umbrales globales de semaforizacion",
)
async def update_global_thresholds(
    body: UmbralesSemaforoRequest,
    current_user=Depends(require_roles("planeacion", "admin_sistema")),
    use_case: UpdateGlobalThresholds = Depends(get_update_global_thresholds_use_case),
) -> UmbralesSemaforoRespuesta:
    thresholds = await use_case.execute(
        UpdateThresholdsCommand(
            green=body.umbral_verde_min,
            yellow=body.umbral_amarillo_min,
            actor_id=current_user.id,
        )
    )
    return UmbralesSemaforoRespuesta.from_domain(thresholds)


@router.patch(
    "/indicadores/{indicator_id}/umbrales",
    summary="Actualizar umbrales personalizados del indicador",
    responses={422: {"model": ErrorResponse, "description": "Umbrales invalidos."}},
)
async def update_indicator_thresholds(
    indicator_id: int,
    body: UmbralesPersonalizadosRequest,
    current_user=Depends(require_roles("planeacion", "admin_sistema")),
    use_case: UpdateIndicatorThresholds = Depends(get_update_indicator_thresholds_use_case),
):
    indicator = await use_case.execute(
        indicator_id,
        body.umbral_verde_min,
        body.umbral_amarillo_min,
        current_user.id,
    )
    from ...indicators_catalog.api.schemas import IndicadorRespuesta

    return IndicadorRespuesta.from_domain(indicator)


@router.get(
    "/indicadores/{indicator_id}/tendencia",
    response_model=list[TendenciaPuntoRespuesta],
    summary="Consultar tendencia historica del indicador",
)
async def indicator_trend(
    indicator_id: int,
    request: Request,
    _current_user=Depends(get_current_user),
) -> list[TendenciaPuntoRespuesta]:
    captures = await request.app.state.capture_repository.list_by_indicator(indicator_id)
    return [
        TendenciaPuntoRespuesta(
            periodo_id=capture.period_id,
            porcentaje_avance=capture.progress_percentage,
            semaforo=capture.semaphore,
        )
        for capture in captures
    ]
