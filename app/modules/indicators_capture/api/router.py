"""Endpoints de captura de avances de indicadores."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status

from app.core.schemas import ErrorResponse
from app.core.security import get_current_user

from ...evidence_management.api.dependencies import get_attach_evidence_use_case
from ...evidence_management.application.dto import AttachEvidenceCommand
from ...evidence_management.application.use_cases.manage_evidence import AttachEvidence
from ...evidence_management.domain.value_objects import FlowEntity
from ..application.dto import EditCaptureCommand, RegisterCaptureCommand, SendCaptureCommand
from ..application.use_cases.manage_capture import EditCapture, RegisterCapture, SendCapture
from .dependencies import (
    get_edit_capture_use_case,
    get_register_capture_use_case,
    get_send_capture_use_case,
)
from .schemas import (
    AdjuntarEvidenciaCapturaRequest,
    CapturaRespuesta,
    EditarCapturaRequest,
    RegistrarCapturaRequest,
)

TAG = "Capturas de indicadores"
router = APIRouter(prefix="/capturas", tags=[TAG])


@router.post(
    "",
    response_model=CapturaRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar captura en borrador",
    responses={
        409: {"model": ErrorResponse, "description": "Periodo cerrado o captura duplicada."},
        422: {"model": ErrorResponse, "description": "Indicador o periodo invalidos."},
    },
)
async def create_capture(
    body: RegistrarCapturaRequest,
    current_user=Depends(get_current_user),
    use_case: RegisterCapture = Depends(get_register_capture_use_case),
) -> CapturaRespuesta:
    capture = await use_case.execute(
        RegisterCaptureCommand(
            indicator_id=body.indicador_id,
            period_id=body.periodo_id,
            capturer_id=current_user.id,
            result=body.resultado,
            source_data=body.datos_fuente,
            activity=body.actividad_realizada,
            observations=body.observaciones,
        )
    )
    return CapturaRespuesta.from_domain(capture)


@router.get(
    "/mis-pendientes",
    response_model=list[CapturaRespuesta],
    summary="Consultar panel personal de capturas",
)
async def list_my_captures(
    request: Request,
    periodo_id: int | None = None,
    current_user=Depends(get_current_user),
) -> list[CapturaRespuesta]:
    captures = await request.app.state.capture_repository.list_by_capturer(
        current_user.id,
        periodo_id,
    )
    return [CapturaRespuesta.from_domain(capture) for capture in captures]


@router.get(
    "/{capture_id}",
    response_model=CapturaRespuesta,
    summary="Consultar captura de indicador",
)
async def get_capture(
    capture_id: int,
    request: Request,
    _current_user=Depends(get_current_user),
) -> CapturaRespuesta:
    capture = await request.app.state.capture_repository.get_by_id(capture_id)
    if capture is None:
        from app.shared.domain.exceptions import ResourceNotFoundError

        raise ResourceNotFoundError("La captura no existe.")
    return CapturaRespuesta.from_domain(capture)


@router.patch(
    "/{capture_id}",
    response_model=CapturaRespuesta,
    summary="Editar captura en borrador",
)
async def edit_capture(
    capture_id: int,
    body: EditarCapturaRequest,
    current_user=Depends(get_current_user),
    use_case: EditCapture = Depends(get_edit_capture_use_case),
) -> CapturaRespuesta:
    capture = await use_case.execute(
        EditCaptureCommand(
            capture_id=capture_id,
            actor_id=current_user.id,
            result=body.resultado,
            source_data=body.datos_fuente,
            activity=body.actividad_realizada,
            observations=body.observaciones,
        )
    )
    return CapturaRespuesta.from_domain(capture)


@router.post(
    "/{capture_id}/enviar",
    response_model=CapturaRespuesta,
    summary="Enviar captura para validacion",
    responses={422: {"model": ErrorResponse, "description": "Resultado o evidencia faltantes."}},
)
async def send_capture(
    capture_id: int,
    current_user=Depends(get_current_user),
    use_case: SendCapture = Depends(get_send_capture_use_case),
) -> CapturaRespuesta:
    capture = await use_case.execute(
        SendCaptureCommand(capture_id=capture_id, actor_id=current_user.id)
    )
    return CapturaRespuesta.from_domain(capture)


@router.post(
    "/{capture_id}/evidencias",
    status_code=status.HTTP_201_CREATED,
    summary="Adjuntar evidencia a una captura",
)
async def attach_capture_evidence(
    capture_id: int,
    body: AdjuntarEvidenciaCapturaRequest,
    request: Request,
    current_user=Depends(get_current_user),
    use_case: AttachEvidence = Depends(get_attach_evidence_use_case),
):
    capture = await request.app.state.capture_repository.get_by_id(capture_id)
    if capture is None:
        from app.shared.domain.exceptions import ResourceNotFoundError

        raise ResourceNotFoundError("La captura no existe.")
    if capture.capturer_id != current_user.id:
        from app.shared.domain.exceptions import ForbiddenError

        raise ForbiddenError("El usuario no es el capturista de la captura.")
    evidence = await use_case.execute(
        AttachEvidenceCommand(
            name=body.nombre,
            description=body.descripcion,
            evidence_date=body.fecha,
            evidence_type=body.tipo,
            path_or_url=body.ruta_o_url,
            entity=FlowEntity.CAPTURE,
            entity_id=capture_id,
            actor_id=current_user.id,
            mime_type=body.mime_type,
            size_bytes=body.tamanio_bytes,
            checksum_sha256=body.checksum_sha256,
        )
    )
    from ...evidence_management.api.schemas import EvidenciaRespuesta

    return EvidenciaRespuesta.from_domain(evidence)
