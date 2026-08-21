"""Endpoints transversales de evidencias."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status

from app.core.schemas import ErrorResponse
from app.core.security import get_current_user
from app.shared.domain.exceptions import ResourceNotFoundError

from ..application.dto import AttachEvidenceCommand, ReplaceEvidenceCommand
from ..application.use_cases.manage_evidence import AttachEvidence, ReplaceEvidence
from ..domain.value_objects import FlowEntity
from .dependencies import get_attach_evidence_use_case, get_replace_evidence_use_case
from .schemas import (
    AdjuntarEvidenciaRequest,
    EvidenciaRespuesta,
    ReemplazarEvidenciaRequest,
    VersionEvidenciaRespuesta,
)

TAG = "Evidencias"
router = APIRouter(prefix="/evidencias", tags=[TAG])


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
    if body.entidad is FlowEntity.CAPTURE:
        capture = await request.app.state.capture_repository.get_by_id(body.entidad_id)
        if capture is None:
            raise ResourceNotFoundError("La captura no existe.")
        capture.ensure_editable(period_is_open=True)
    evidence = await use_case.execute(
        AttachEvidenceCommand(
            name=body.nombre,
            description=body.descripcion,
            evidence_date=body.fecha,
            evidence_type=body.tipo,
            path_or_url=body.ruta_o_url,
            entity=body.entidad,
            entity_id=body.entidad_id,
            actor_id=current_user.id,
            mime_type=body.mime_type,
            size_bytes=body.tamanio_bytes,
            checksum_sha256=body.checksum_sha256,
        )
    )
    return EvidenciaRespuesta.from_domain(evidence)


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
            actor_id=current_user.id,
            mime_type=body.mime_type,
            size_bytes=body.tamanio_bytes,
            checksum_sha256=body.checksum_sha256,
        )
    )


@router.get(
    "/{evidence_id}/versiones",
    response_model=list[VersionEvidenciaRespuesta],
    summary="Consultar versiones append-only de una evidencia",
)
async def list_evidence_versions(
    evidence_id: int,
    request: Request,
    _current_user=Depends(get_current_user),
) -> list[VersionEvidenciaRespuesta]:
    if await request.app.state.evidence_repository.get(evidence_id) is None:
        raise ResourceNotFoundError("La evidencia no existe.")
    versions = await request.app.state.evidence_repository.list_versions(evidence_id)
    return [
        VersionEvidenciaRespuesta(
            numero=index,
            ruta_o_url=item.path_or_url,
            mime_type=item.mime_type,
            tamanio_bytes=item.size_bytes,
            checksum_sha256=item.checksum_sha256,
            fecha=item.created_at,
            usuario_id=item.user_id,
        )
        for index, item in enumerate(versions, start=1)
    ]
