"""Construccion del contrato publico de evidencias."""

from __future__ import annotations

from ..domain.value_objects import EvidenceType
from .schemas import EvidenciaRespuesta, VersionEvidenciaRespuesta


def public_evidence_reference(
    path_or_url: str,
    evidence_type: EvidenceType,
    api_prefix: str,
) -> str:
    if evidence_type is EvidenceType.FILE and not path_or_url.startswith(
        ("http://", "https://", "/")
    ):
        return f"{api_prefix.rstrip('/')}/archivos/{path_or_url}"
    return path_or_url


async def present_evidence(evidence, repository, api_prefix: str) -> EvidenciaRespuesta:
    versions = await repository.list_versions(evidence.id)
    current = versions[-1] if versions else None
    version_response = None
    if current is not None:
        version_response = VersionEvidenciaRespuesta(
            numero=len(versions),
            ruta_o_url=public_evidence_reference(
                current.path_or_url,
                evidence.evidence_type,
                api_prefix,
            ),
            mime_type=current.mime_type,
            tamanio_bytes=current.size_bytes,
            checksum_sha256=current.checksum_sha256,
            fecha=current.created_at,
            usuario_id=current.user_id,
        )
    return EvidenciaRespuesta.from_domain(evidence, version_response)
