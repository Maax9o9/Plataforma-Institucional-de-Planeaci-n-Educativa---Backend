"""Endpoints de captura de avances de indicadores."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.core.authorization import actor_from_user, ensure_owner_or_planning
from app.core.schemas import ErrorResponse
from app.core.security import get_current_user
from app.shared.domain.exceptions import ForbiddenError, ResourceNotFoundError

from ...evidence_management.api.dependencies import (
    get_attach_evidence_use_case,
    get_evidence_access_control,
)
from ...evidence_management.api.schemas import EvidenciaRespuesta
from ...evidence_management.application.dto import AttachEvidenceCommand, UnlinkEvidenceCommand
from ...evidence_management.application.use_cases.link_evidence import UnlinkEvidence
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
    CapturaPendienteRespuesta,
    CapturaRespuesta,
    EditarCapturaRequest,
    IndicadorPendienteRespuesta,
    PaginaCapturasRespuesta,
    PaginaPendientesRespuesta,
    PeriodoPendienteRespuesta,
    RegistrarCapturaRequest,
)

TAG = "Capturas de indicadores"
router = APIRouter(prefix="/capturas", tags=[TAG])


@router.get(
    "",
    response_model=PaginaCapturasRespuesta,
    summary="Consultar bandeja paginada de capturas",
)
async def list_captures(
    request: Request,
    estado: str | None = Query(default=None),
    area_id: int | None = Query(default=None),
    indicador_id: int | None = Query(default=None),
    periodo_id: int | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    current_user=Depends(get_current_user),
) -> PaginaCapturasRespuesta:
    items = await request.app.state.capture_repository.list_all()
    if not current_user.has_any_role({"planeacion", "admin_sistema"}):
        items = [item for item in items if item.capturer_id == current_user.id]
    if estado is not None:
        items = [item for item in items if item.status.value == estado]
    if indicador_id is not None:
        items = [item for item in items if item.indicator_id == indicador_id]
    if periodo_id is not None:
        items = [item for item in items if item.period_id == periodo_id]
    if area_id is not None:
        filtered = []
        for item in items:
            indicator = await request.app.state.indicator_repository.get_by_id(item.indicator_id)
            if indicator is not None and indicator.area_id == area_id:
                filtered.append(item)
        items = filtered
    total = len(items)
    return PaginaCapturasRespuesta(
        items=[CapturaRespuesta.from_domain(item) for item in items[offset : offset + limit]],
        total=total,
        offset=offset,
        limit=limit,
    )


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
    response_model=PaginaPendientesRespuesta,
    summary="Consultar panel personal de capturas",
)
async def list_my_captures(
    request: Request,
    periodo_id: int | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    current_user=Depends(get_current_user),
) -> PaginaPendientesRespuesta:
    indicators = [
        item
        for item in await request.app.state.indicator_repository.list(active_only=True)
        if item.responsible_id == current_user.id
    ]
    periods = [
        item
        for item in await request.app.state.period_repository.list()
        if item.period_type.value == "indicadores" and item.status.value == "abierto"
    ]
    if periodo_id is not None:
        periods = [item for item in periods if item.id == periodo_id]
    rows = []
    for indicator in indicators:
        for period in periods:
            if (
                period.periodicity is not None
                and period.periodicity.value != indicator.periodicity.value
            ):
                continue
            capture = await request.app.state.capture_repository.get_by_indicator_period(
                indicator.id, period.id
            )
            goal = await request.app.state.indicator_repository.get_goal(indicator.id, period.id)
            evidence_total = 0
            if capture is not None:
                evidence_total = len(
                    await request.app.state.evidence_repository.list_for(
                        FlowEntity.CAPTURE, capture.id
                    )
                )
            rows.append(
                CapturaPendienteRespuesta(
                    indicador=IndicadorPendienteRespuesta(
                        id=indicator.id,
                        clave=indicator.key,
                        nombre=indicator.name,
                        unidad_medida=indicator.unit,
                    ),
                    periodo=PeriodoPendienteRespuesta(
                        id=period.id,
                        etiqueta=period.name,
                        fecha_limite=period.ends_on,
                        estado=period.status.value,
                    ),
                    meta=goal.value if goal else None,
                    captura=CapturaRespuesta.from_domain(capture) if capture else None,
                    evidencias_total=evidence_total,
                )
            )
    total = len(rows)
    return PaginaPendientesRespuesta(
        items=rows[offset : offset + limit], total=total, offset=offset, limit=limit
    )


@router.get(
    "/{capture_id}",
    response_model=CapturaRespuesta,
    summary="Consultar captura de indicador",
)
async def get_capture(
    capture_id: int,
    request: Request,
    current_user=Depends(get_current_user),
) -> CapturaRespuesta:
    capture = await request.app.state.capture_repository.get_by_id(capture_id)
    if capture is None:
        from app.shared.domain.exceptions import ResourceNotFoundError

        raise ResourceNotFoundError("La captura no existe.")
    ensure_owner_or_planning(current_user, capture.capturer_id)
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
            actor=actor_from_user(current_user),
            mime_type=body.mime_type,
            size_bytes=body.tamanio_bytes,
            checksum_sha256=body.checksum_sha256,
        )
    )
    return EvidenciaRespuesta.from_domain(evidence)


@router.get(
    "/{capture_id}/evidencias",
    response_model=list[EvidenciaRespuesta],
    summary="Consultar evidencias vinculadas a una captura",
)
async def list_capture_evidence(
    capture_id: int,
    request: Request,
    current_user=Depends(get_current_user),
) -> list[EvidenciaRespuesta]:
    capture = await request.app.state.capture_repository.get_by_id(capture_id)
    if capture is None:
        raise ResourceNotFoundError("La captura no existe.")
    if capture.capturer_id != current_user.id and not current_user.has_any_role(
        {"planeacion", "admin_sistema"}
    ):
        raise ForbiddenError()
    evidences = await request.app.state.evidence_repository.list_for(
        FlowEntity.CAPTURE, capture_id
    )
    return [EvidenciaRespuesta.from_domain(item) for item in evidences]


@router.delete(
    "/{capture_id}/evidencias/{evidence_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Desvincular evidencia de una captura",
)
async def unlink_capture_evidence(
    capture_id: int,
    evidence_id: int,
    request: Request,
    current_user=Depends(get_current_user),
) -> Response:
    capture = await request.app.state.capture_repository.get_by_id(capture_id)
    if capture is None:
        raise ResourceNotFoundError("La captura no existe.")
    await UnlinkEvidence(
        request.app.state.evidence_repository,
        request.app.state.event_bus,
        get_evidence_access_control(request),
        request.app.state.unit_of_work,
    ).execute(
        UnlinkEvidenceCommand(
            evidence_id=evidence_id,
            entity=FlowEntity.CAPTURE,
            entity_id=capture_id,
            actor=actor_from_user(current_user),
        )
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
