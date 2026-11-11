from __future__ import annotations

import re
from dataclasses import dataclass

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

MIME_POR_EXTENSION = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".docx": DOCX_MIME,
}

LARGO_DEL_IDENTIFICADOR = 32

_LAS_EXTENSIONES = "|".join(sorted(una.removeprefix(".") for una in MIME_POR_EXTENSION))

NOMBRE_DE_ARCHIVO_CARGADO = re.compile(
    rf"^[0-9a-f]{{{LARGO_DEL_IDENTIFICADOR}}}\.(?:{_LAS_EXTENSIONES})$"
)


@dataclass(frozen=True)
class ArchivoCargado:
    ruta: str
    mime_type: str
    tamanio_bytes: int


def el_tipo_del_archivo_cargado(ruta: str) -> str | None:
    if not NOMBRE_DE_ARCHIVO_CARGADO.fullmatch(ruta):
        return None
    return MIME_POR_EXTENSION[f".{ruta.rsplit('.', 1)[1]}"]
