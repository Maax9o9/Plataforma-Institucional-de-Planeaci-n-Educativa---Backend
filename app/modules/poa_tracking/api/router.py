"""Endpoints de seguimiento cuatrimestral POA."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Request, status

from app.core.authorization import actor_from_user, ensure_owner_or_planning
from app.core.security import get_current_user, require_roles
from app.shared.domain.exceptions import ResourceNotFoundError

from ...evidence_management.api.dependencies import (
    get_attach_evidence_use_case,
    get_evidence_access_control,
)
from ...evidence_management.application.dto import (
    AttachEvidenceCommand,
    LinkExistingEvidenceCommand,
)
from ...evidence_management.application.use_cases.link_evidence import LinkExistingEvidence
from ...evidence_management.application.use_cases.manage_evidence import AttachEvidence
from ...evidence_management.domain.value_objects import FlowEntity
from ..application.dto import EditAdvanceCommand, RegisterAdvanceCommand, SendAdvanceCommand
from ..application.use_cases.manage_advance import EditAdvance, RegisterAdvance, SendAdvance
from .dependencies import (
    get_edit_advance_use_case,
    get_register_advance_use_case,
    get_send_advance_use_case,
)
from .schemas import (
    AdjuntarEvidenciaAvanceRequest,
    AvanceRespuesta,
    EditarAvanceRequest,
    RegistrarAvanceRequest,
    VincularEvidenciaRequest,
)

TAG = "Seguimiento POA"
router = APIRouter(prefix="/poa", tags=[TAG])


@router.post(
    "/avances",
    response_model=AvanceRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar avance POA",
)
async def create_advance(
    body: RegistrarAvanceRequest,
    current_user=Depends(require_roles("responsable_area", "planeacion", "admin_sistema")),
    use_case: RegisterAdvance = Depends(get_register_advance_use_case),
) -> AvanceRespuesta:
    item = await use_case.execute(
        RegisterAdvanceCommand(
            activity_id=body.actividad_id,
            quarter=body.cuatrimestre,
            period_id=body.periodo_id,
            actor=actor_from_user(current_user),
            scheduled=body.programado,
            achieved=body.alcanzado,
            observations=body.observaciones,
            criteria_ids=body.criterio_seaes_ids,
        )
    )
    return AvanceRespuesta.from_domain(item)


@router.get(
    "/avances/mis", response_model=list[AvanceRespuesta], summary="Consultar mis avances POA"
)
async def list_my_advances(
    request: Request,
    current_user=Depends(get_current_user),
) -> list[AvanceRespuesta]:
    items = await request.app.state.poa_advance_repository.list_by_capturer(current_user.id)
    return [AvanceRespuesta.from_domain(item) for item in items]


@router.get("/avances/{advance_id}", response_model=AvanceRespuesta, summary="Consultar avance POA")
async def get_advance(
    advance_id: int,
    request: Request,
    current_user=Depends(get_current_user),
) -> AvanceRespuesta:
    item = await request.app.state.poa_advance_repository.get_by_id(advance_id)
    if item is None:
        raise ResourceNotFoundError("El avance POA no existe.")
    ensure_owner_or_planning(current_user, item.capturer_id)
    return AvanceRespuesta.from_domain(item)


@router.patch("/avances/{advance_id}", response_model=AvanceRespuesta, summary="Editar avance POA")
async def edit_advance(
    advance_id: int,
    body: EditarAvanceRequest,
    current_user=Depends(get_current_user),
    use_case: EditAdvance = Depends(get_edit_advance_use_case),
) -> AvanceRespuesta:
    item = await use_case.execute(
        EditAdvanceCommand(
            advance_id=advance_id,
            actor_id=current_user.id,
            scheduled=body.programado,
            achieved=body.alcanzado,
            observations=body.observaciones,
            criteria_ids=body.criterio_seaes_ids,
        )
    )
    return AvanceRespuesta.from_domain(item)


@router.post(
    "/avances/{advance_id}/enviar", response_model=AvanceRespuesta, summary="Enviar avance POA"
)
async def send_advance(
    advance_id: int,
    current_user=Depends(get_current_user),
    use_case: SendAdvance = Depends(get_send_advance_use_case),
) -> AvanceRespuesta:
    item = await use_case.execute(
        SendAdvanceCommand(advance_id=advance_id, actor_id=current_user.id)
    )
    return AvanceRespuesta.from_domain(item)


@router.get(
    "/actividades/{activity_id}/acumulado",
    response_model=dict,
    summary="Consultar acumulado de tres cuatrimestres",
)
async def accumulated(
    activity_id: int,
    request: Request,
    current_user=Depends(
        require_roles("planeacion", "admin_sistema", "rectoria", "responsable_area")
    ),
):
    activity = await request.app.state.poa_repository.get_activity(activity_id)
    if activity is None:
        raise ResourceNotFoundError("La actividad POA no existe.")
    if not current_user.has_any_role({"planeacion", "admin_sistema", "rectoria"}):
        objective = await request.app.state.poa_repository.get_objective(activity.objective_id)
        process = (
            await request.app.state.poa_repository.get_process(objective.process_id)
            if objective
            else None
        )
        if process is None or process.area_id != current_user.area_id:
            from app.shared.domain.exceptions import ForbiddenError

            raise ForbiddenError("La actividad POA no pertenece al area del usuario.")
    items = await request.app.state.poa_advance_repository.list_by_activity(activity_id)
    validated = [item for item in items if item.status.value == "validado"]
    achieved = sum((item.achieved or Decimal(0) for item in validated), Decimal(0))
    percentage = (achieved / activity.annual_goal * Decimal(100)) if activity.annual_goal else None
    return {
        "disponible": bool(validated),
        "actividad_id": activity_id,
        "meta_anual": activity.annual_goal,
        "alcanzado_acumulado": achieved,
        "porcentaje_meta": percentage,
        "avances": [AvanceRespuesta.from_domain(item).model_dump() for item in items],
    }


@router.post(
    "/avances/{advance_id}/evidencias",
    status_code=status.HTTP_201_CREATED,
    summary="Adjuntar evidencia a avance POA",
)
async def attach_evidence(
    advance_id: int,
    body: AdjuntarEvidenciaAvanceRequest,
    request: Request,
    current_user=Depends(get_current_user),
    use_case: AttachEvidence = Depends(get_attach_evidence_use_case),
):
    advance = await request.app.state.poa_advance_repository.get_by_id(advance_id)
    if advance is None:
        raise ResourceNotFoundError("El avance POA no existe.")
    item = await use_case.execute(
        AttachEvidenceCommand(
            name=body.nombre,
            description=body.descripcion,
            evidence_date=body.fecha,
            evidence_type=body.tipo,
            path_or_url=body.ruta_o_url,
            entity=FlowEntity.POA_ADVANCE,
            entity_id=advance_id,
            actor=actor_from_user(current_user),
        )
    )
    from ...evidence_management.api.schemas import EvidenciaRespuesta

    return EvidenciaRespuesta.from_domain(item)


@router.post(
    "/avances/{advance_id}/evidencias/vincular",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Reutilizar evidencia en avance POA",
)
async def link_evidence(
    advance_id: int,
    body: VincularEvidenciaRequest,
    request: Request,
    current_user=Depends(get_current_user),
):
    advance = await request.app.state.poa_advance_repository.get_by_id(advance_id)
    if advance is None:
        raise ResourceNotFoundError("El avance POA no existe.")
    await LinkExistingEvidence(
        request.app.state.evidence_repository,
        request.app.state.event_bus,
        get_evidence_access_control(request),
        request.app.state.unit_of_work,
    ).execute(
        LinkExistingEvidenceCommand(
            evidence_id=body.evidencia_id,
            entity=FlowEntity.POA_ADVANCE,
            entity_id=advance_id,
            actor=actor_from_user(current_user),
        )
    )


@router.get(
    "/ejercicios/{exercise_id}/evidencias-disponibles",
    summary="Consultar evidencias reutilizables del ejercicio POA",
)
async def reusable_evidence(
    exercise_id: int,
    request: Request,
    current_user=Depends(get_current_user),
):
    from ...evidence_management.api.schemas import EvidenciaRespuesta

    evidences = await get_evidence_access_control(request).list_reusable_for_exercise(
        exercise_id, actor_from_user(current_user)
    )
    return [EvidenciaRespuesta.from_domain(item) for item in evidences]
