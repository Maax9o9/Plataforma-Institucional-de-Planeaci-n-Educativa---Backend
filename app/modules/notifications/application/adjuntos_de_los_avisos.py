from __future__ import annotations

from ..domain.entities import Aviso


class LosAdjuntosDeLosAvisos:
    def __init__(self, avisos, notifications) -> None:
        self.avisos = avisos
        self.notifications = notifications

    async def puede_abrirlo(self, ruta: str, *, usuario_id: int, redacta_avisos: bool) -> bool:
        aviso = await self._el_que_lo_lleva(ruta)
        if aviso is None:
            return False
        if redacta_avisos:
            return True
        entregas = await self.notifications.deliveries_of([aviso.id])
        return any(una.usuario_id == usuario_id for una in entregas)

    async def _el_que_lo_lleva(self, ruta: str) -> Aviso | None:
        for aviso in await self.avisos.list():
            if any(adjunto.ruta_o_url == ruta for adjunto in aviso.adjuntos):
                return aviso
        return None
