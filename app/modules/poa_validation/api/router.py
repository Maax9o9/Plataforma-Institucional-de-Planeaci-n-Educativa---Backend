from fastapi import APIRouter, Depends

from app.core.schemas import ErrorResponse
from app.core.security import require_roles

from ...poa_tracking.api.schemas import AvanceRespuesta
from ..application.dto import RejectPoaAdvanceCommand, ValidatePoaAdvanceCommand
from ..application.use_cases.validate_advance import RejectPoaAdvance, ValidatePoaAdvance
from .dependencies import get_reject_poa_advance_use_case, get_validate_poa_advance_use_case
from .schemas import RechazarAvanceRequest

router = APIRouter(prefix="/poa/avances", tags=["Validacion POA"])


@router.post(
    "/{advance_id}/validar",
    response_model=AvanceRespuesta,
    summary="Validar avance POA",
    responses={422: {"model": ErrorResponse, "description": "Transicion invalida."}},
)
async def validate_advance(
    advance_id: int,
    current_user=Depends(require_roles("planeacion", "admin_sistema")),
    use_case: ValidatePoaAdvance = Depends(get_validate_poa_advance_use_case),
) -> AvanceRespuesta:
    item = await use_case.execute(
        ValidatePoaAdvanceCommand(advance_id=advance_id, user_id=current_user.id)
    )
    return AvanceRespuesta.from_domain(item)


@router.post(
    "/{advance_id}/rechazar",
    response_model=AvanceRespuesta,
    summary="Rechazar avance POA con comentario",
)
async def reject_advance(
    advance_id: int,
    body: RechazarAvanceRequest,
    current_user=Depends(require_roles("planeacion", "admin_sistema")),
    use_case: RejectPoaAdvance = Depends(get_reject_poa_advance_use_case),
) -> AvanceRespuesta:
    item = await use_case.execute(
        RejectPoaAdvanceCommand(
            advance_id=advance_id,
            user_id=current_user.id,
            comment=body.comentario,
        )
    )
    return AvanceRespuesta.from_domain(item)
