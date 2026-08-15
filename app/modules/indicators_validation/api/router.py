"""Endpoints del flujo de validacion de capturas."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.core.schemas import ErrorResponse
from app.core.security import get_current_user, require_roles
from app.shared.domain.exceptions import ForbiddenError, ResourceNotFoundError

from ...indicators_capture.api.schemas import CapturaRespuesta
from ..application.dto import RejectCaptureCommand, ValidateCaptureCommand
from ..application.use_cases.validate_capture import RejectCapture, ValidateCapture
from .dependencies import get_reject_capture_use_case, get_validate_capture_use_case
from .schemas import CambioEstadoRespuesta, RechazarCapturaRequest

TAG = "Validacion de capturas"
router = APIRouter(prefix="/capturas", tags=[TAG])


@router.post(
    "/{capture_id}/validar",
    response_model=CapturaRespuesta,
    summary="Validar captura enviada",
    responses={
        403: {"model": ErrorResponse, "description": "Rol insuficiente."},
        422: {"model": ErrorResponse, "description": "Transicion invalida."},
    },
)
async def validate_capture(
    capture_id: int,
    current_user=Depends(require_roles("planeacion", "admin_sistema")),
    use_case: ValidateCapture = Depends(get_validate_capture_use_case),
) -> CapturaRespuesta:
    capture = await use_case.execute(
        ValidateCaptureCommand(capture_id=capture_id, user_id=current_user.id)
    )
    return CapturaRespuesta.from_domain(capture)


@router.post(
    "/{capture_id}/rechazar",
    response_model=CapturaRespuesta,
    summary="Rechazar captura con comentario",
    responses={
        403: {"model": ErrorResponse, "description": "Rol insuficiente."},
        422: {"model": ErrorResponse, "description": "Comentario o transicion invalidos."},
    },
)
async def reject_capture(
    capture_id: int,
    body: RechazarCapturaRequest,
    current_user=Depends(require_roles("planeacion", "admin_sistema")),
    use_case: RejectCapture = Depends(get_reject_capture_use_case),
) -> CapturaRespuesta:
    capture = await use_case.execute(
        RejectCaptureCommand(
            capture_id=capture_id,
            user_id=current_user.id,
            comment=body.comentario,
        )
    )
    return CapturaRespuesta.from_domain(capture)


@router.get(
    "/{capture_id}/historial",
    response_model=list[CambioEstadoRespuesta],
    summary="Consultar historial de estados",
)
async def capture_history(
    capture_id: int,
    request: Request,
    current_user=Depends(get_current_user),
) -> list[CambioEstadoRespuesta]:
    capture = await request.app.state.capture_repository.get_by_id(capture_id)
    if capture is None:
        raise ResourceNotFoundError("La captura no existe.")
    if capture.capturer_id != current_user.id and not current_user.has_any_role(
        {"planeacion", "admin_sistema"}
    ):
        raise ForbiddenError()
    changes = await request.app.state.state_change_repository.list_for_capture(capture_id)
    return [CambioEstadoRespuesta.from_domain(change) for change in changes]
