"""Endpoints transversales de evidencias."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.core.schemas import ErrorResponse
from app.core.security import get_current_user

from ..application.dto import AttachEvidenceCommand, ReplaceEvidenceCommand
from ..application.use_cases.manage_evidence import AttachEvidence, ReplaceEvidence
from .dependencies import get_attach_evidence_use_case, get_replace_evidence_use_case
from .schemas import (
    AdjuntarEvidenciaRequest,
    EvidenciaRespuesta,
    ReemplazarEvidenciaRequest,
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
