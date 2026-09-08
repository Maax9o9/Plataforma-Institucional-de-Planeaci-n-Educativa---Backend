"""Endpoints transversales de evidencias."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, status

from app.core.authorization import actor_from_user
from app.core.schemas import ErrorResponse
from app.core.security import get_current_user
from app.shared.domain.exceptions import ResourceNotFoundError

from ..application.dto import AttachEvidenceCommand, ReplaceEvidenceCommand
from ..application.use_cases.manage_evidence import AttachEvidence, ReplaceEvidence
from ..domain.value_objects import FlowEntity
from .dependencies import (
    get_attach_evidence_use_case,
    get_evidence_access_control,
    get_replace_evidence_use_case,
)
from .presenters import present_evidence, public_evidence_reference
from .schemas import (
    AdjuntarEvidenciaRequest,
    EvidenciaRespuesta,
    PaginaVersionesEvidenciaRespuesta,
    ReemplazarEvidenciaRequest,
    VersionEvidenciaRespuesta,
)

TAG = "Evidencias"
router = APIRouter(prefix="/evidencias", tags=[TAG])


@router.get(
    "",
    response_model=list[EvidenciaRespuesta],
    summary="Consultar evidencias vinculadas a un registro",
)
async def list_evidences_for_target(
    entidad: Literal[FlowEntity.CAPTURE, FlowEntity.POA_FORM_FOLLOW_UP],
    entidad_id: int,
    request: Request,
    current_user=Depends(get_current_user),
) -> list[EvidenciaRespuesta]:
    actor = actor_from_user(current_user)
    await get_evidence_access_control(request).ensure_target_viewable(
        entidad, entidad_id, actor
    )
    items = await request.app.state.evidence_repository.list_for(entidad, entidad_id)
    return [
        await present_evidence(
            item,
            request.app.state.evidence_repository,
            request.app.state.settings.api_v1_prefix,
        )
        for item in items
    ]


@router.post(
    "",
    response_model=EvidenciaRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Adjuntar evidencia",
    responses={
        401: {"model": ErrorResponse, "description": "Autenticacion requerida."},
        409: {"model": ErrorResponse, "description": "Vinculo duplicado."},
    },
)
async def attach_evidence(
    body: AdjuntarEvidenciaRequest,
    request: Request,
    current_user=Depends(get_current_user),
    use_case: AttachEvidence = Depends(get_attach_evidence_use_case),
) -> EvidenciaRespuesta:
    evidence = await use_case.execute(
        AttachEvidenceCommand(
            name=body.nombre,
            description=body.descripcion,
            evidence_date=body.fecha,
            evidence_type=body.tipo,
            path_or_url=body.ruta_o_url,
            entity=body.entidad,
            entity_id=body.entidad_id,
            actor=actor_from_user(current_user),
            mime_type=body.mime_type,
            size_bytes=body.tamanio_bytes,
            checksum_sha256=body.checksum_sha256,
        )
    )
    return await present_evidence(
        evidence,
        request.app.state.evidence_repository,
        request.app.state.settings.api_v1_prefix,
    )


@router.put(
    "/{evidence_id}/version",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Reemplazar evidencia conservando versiones",
    responses={404: {"model": ErrorResponse, "description": "Evidencia inexistente."}},
)
async def replace_evidence(
    evidence_id: int,
    body: ReemplazarEvidenciaRequest,
    current_user=Depends(get_current_user),
    use_case: ReplaceEvidence = Depends(get_replace_evidence_use_case),
) -> None:
    await use_case.execute(
        ReplaceEvidenceCommand(
            evidence_id=evidence_id,
            path_or_url=body.ruta_o_url,
            actor=actor_from_user(current_user),
            mime_type=body.mime_type,
            size_bytes=body.tamanio_bytes,
            checksum_sha256=body.checksum_sha256,
        )
    )


@router.get(
    "/{evidence_id}/versiones",
    response_model=PaginaVersionesEvidenciaRespuesta,
    summary="Consultar versiones append-only de una evidencia",
)
async def list_evidence_versions(
    evidence_id: int,
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    order: Literal["asc", "desc"] = Query(default="desc"),
    current_user=Depends(get_current_user),
) -> PaginaVersionesEvidenciaRespuesta:
    await get_evidence_access_control(request).ensure_can_view(
        evidence_id, actor_from_user(current_user)
    )
    evidence = await request.app.state.evidence_repository.get(evidence_id)
    if evidence is None:
        raise ResourceNotFoundError("La evidencia no existe.")
    versions, total = await request.app.state.evidence_repository.list_versions_page(
        evidence_id,
        offset=offset,
        limit=limit,
        descending=order == "desc",
    )
    rendered = [
        VersionEvidenciaRespuesta(
            numero=number,
            ruta_o_url=public_evidence_reference(
                item.path_or_url,
                evidence.evidence_type,
                request.app.state.settings.api_v1_prefix,
            ),
            mime_type=item.mime_type,
            tamanio_bytes=item.size_bytes,
            checksum_sha256=item.checksum_sha256,
            fecha=item.created_at,
            usuario_id=item.user_id,
        )
        for number, item in versions
    ]
    return PaginaVersionesEvidenciaRespuesta(
        items=rendered,
        total=total,
        offset=offset,
        limit=limit,
    )
