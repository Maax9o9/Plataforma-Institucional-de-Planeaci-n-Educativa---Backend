from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from app.shared.domain.calendar import institutional_today

from ..domain.entities import (
    Aviso,
    AvisoConSusCifras,
    LecturaPorArea,
    Notification,
)


@dataclass(frozen=True)
class EntregaConSuAviso:
    entrega: Notification
    aviso: Aviso | None


class ElBuzon:
    def __init__(
        self, notifications, avisos, today: Callable[[], date] = institutional_today
    ) -> None:
        self.notifications = notifications
        self.avisos = avisos
        self.today = today

    async def de_la_persona(
        self, usuario_id: int, *, solo_pendientes: bool
    ) -> list[EntregaConSuAviso]:
        entregas = await self.notifications.list_for_user(usuario_id, unread_only=solo_pendientes)
        redactados = await self.avisos.get_many(
            {una.aviso_id for una in entregas if una.aviso_id is not None}
        )
        if solo_pendientes:
            hoy = self.today()
            entregas = [
                una
                for una in entregas
                if una.aviso_id not in redactados or redactados[una.aviso_id].vigente_el(hoy)
            ]
        return [
            EntregaConSuAviso(entrega=una, aviso=redactados.get(una.aviso_id)) for una in entregas
        ]


class LasCifrasDeLectura:
    def __init__(self, avisos, notifications, users, areas) -> None:
        self.avisos = avisos
        self.notifications = notifications
        self.users = users
        self.areas = areas

    async def de_los_avisos(self) -> list[AvisoConSusCifras]:
        redactados = await self.avisos.list()
        entregas = await self.notifications.deliveries_of([uno.id for uno in redactados])
        el_area_de = {
            persona.id: persona.area_id for persona in await self.users.list(active_only=False)
        }
        el_nombre_de = {area.id: area.name for area in await self.areas.list(active_only=False)}
        por_aviso: dict[int, dict[int | None, list[bool]]] = {uno.id: {} for uno in redactados}
        for entrega in entregas:
            area_id = el_area_de.get(entrega.usuario_id)
            por_aviso[entrega.aviso_id].setdefault(area_id, []).append(entrega.leida)
        cifras = []
        for aviso in redactados:
            areas = por_aviso[aviso.id]
            cifras.append(
                AvisoConSusCifras(
                    aviso=aviso,
                    entregados=sum(len(leidas) for leidas in areas.values()),
                    leidos=sum(sum(leidas) for leidas in areas.values()),
                    por_area=tuple(
                        LecturaPorArea(
                            area_id=area_id,
                            area=None if area_id is None else el_nombre_de.get(area_id),
                            entregados=len(leidas),
                            leidos=sum(leidas),
                        )
                        for area_id, leidas in sorted(
                            areas.items(), key=lambda par: (par[0] is None, par[0] or 0)
                        )
                    ),
                )
            )
        return cifras
