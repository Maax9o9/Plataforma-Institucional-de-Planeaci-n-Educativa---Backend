from __future__ import annotations

from pathlib import Path

from app.shared.domain.archivos_cargados import ArchivoCargado, el_tipo_del_archivo_cargado


class StoredUploadedFiles:
    def __init__(self, settings) -> None:
        self.settings = settings

    async def describe(self, ruta: str) -> ArchivoCargado | None:
        mime_type = el_tipo_del_archivo_cargado(ruta)
        if mime_type is None:
            return None
        archivo = Path(self.settings.upload_directory) / ruta
        if not archivo.is_file():
            return None
        return ArchivoCargado(ruta=ruta, mime_type=mime_type, tamanio_bytes=archivo.stat().st_size)
