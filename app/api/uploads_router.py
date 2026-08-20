"""Carga segura de archivos para evidencias."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from pydantic import BaseModel

from app.core.security import get_current_user
from app.shared.domain.exceptions import PayloadTooLargeError, UnsupportedMediaTypeError

router = APIRouter(prefix="/archivos", tags=["Evidencias"])

SIGNATURES = (
    (b"%PDF-", "application/pdf", ".pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
)


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
    _current_user=Depends(get_current_user),
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
    destination.write_bytes(content)
    return ArchivoRespuesta(
        id=file_id,
        ruta=f"{file_id}{extension}",
        mime_type=mime_type,
        tamanio_bytes=len(content),
        checksum_sha256=sha256(content).hexdigest(),
    )
