"""Carga segura de archivos para evidencias."""

from __future__ import annotations

import re
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.core.authorization import actor_from_user
from app.core.security import get_current_user, require_roles
from app.modules.evidence_management.api.dependencies import get_evidence_access_control
from app.shared.domain.exceptions import (
    PayloadTooLargeError,
    ResourceNotFoundError,
    UnsupportedMediaTypeError,
)

router = APIRouter(prefix="/archivos", tags=["Evidencias"])

SIGNATURES = (
    (b"%PDF-", "application/pdf", ".pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
)
SAFE_FILE_NAME = re.compile(r"^[0-9a-f]{32}\.(?:pdf|png|jpg)$")


class ArchivoRespuesta(BaseModel):
    id: str
    ruta: str
    mime_type: str
    tamanio_bytes: int
    checksum_sha256: str


def _detect_type(content: bytes) -> tuple[str, str]:
    for signature, mime_type, extension in SIGNATURES:
        if content.startswith(signature):
            return mime_type, extension
    raise UnsupportedMediaTypeError()


@router.post(
    "",
    response_model=ArchivoRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Cargar archivo seguro para una evidencia",
)
async def upload_file(
    request: Request,
    archivo: UploadFile = File(...),
    _current_user=Depends(
        require_roles(
            "responsable_area",
            "planeacion",
            "planeacion_admin",
            "capturista_poa",
            "admin_sistema",
        )
    ),
) -> ArchivoRespuesta:
    settings = request.app.state.settings
    content = await archivo.read(settings.upload_max_bytes + 1)
    if len(content) > settings.upload_max_bytes:
        raise PayloadTooLargeError(
            details={"max_bytes": settings.upload_max_bytes}
        )
    mime_type, extension = _detect_type(content)
    file_id = uuid4().hex
    storage = Path(settings.upload_directory).resolve()
    storage.mkdir(parents=True, exist_ok=True)
    destination = storage / f"{file_id}{extension}"
    await run_in_threadpool(destination.write_bytes, content)
    return ArchivoRespuesta(
        id=file_id,
        ruta=f"{file_id}{extension}",
        mime_type=mime_type,
        tamanio_bytes=len(content),
        checksum_sha256=sha256(content).hexdigest(),
    )


@router.get(
    "/{file_name}",
    response_class=FileResponse,
    summary="Descargar un archivo de evidencia autorizado",
)
async def download_file(
    file_name: str,
    request: Request,
    current_user=Depends(get_current_user),
):
    if not SAFE_FILE_NAME.fullmatch(file_name):
        raise ResourceNotFoundError("El archivo no existe.")
    evidence_id = await request.app.state.evidence_repository.find_evidence_id_by_path(file_name)
    if evidence_id is None:
        raise ResourceNotFoundError("El archivo no esta vinculado a una evidencia.")
    await get_evidence_access_control(request).ensure_can_view(
        evidence_id, actor_from_user(current_user)
    )
    storage = Path(request.app.state.settings.upload_directory).resolve()
    source = (storage / file_name).resolve()
    if not source.is_relative_to(storage) or not source.is_file():
        raise ResourceNotFoundError("El archivo no existe.")
    media_type = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
    }[source.suffix]
    return FileResponse(source, media_type=media_type, filename=file_name)
