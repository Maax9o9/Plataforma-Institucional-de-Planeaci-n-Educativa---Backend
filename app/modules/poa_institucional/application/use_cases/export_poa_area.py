from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.modules.institutional_catalogs.domain.strategic_tree_entities import StrategicNode
from app.shared.domain.calendar import institutional_today
from app.shared.domain.exceptions import ResourceNotFoundError

from ...domain.entities import Activity, PoaArea, PoaAreaStatus
from ...domain.impresion import PoaParaImprimir, armar_el_poa_para_imprimir

EL_POA_NO_ESTA_ABIERTO = (
    "El área todavía no tiene habilitado el registro del Programa Operativo Anual en este "
    "ejercicio, por lo que no hay nada que imprimir."
)

SIN_AREA = "Esa área no está en la estructura de la universidad."


@dataclass(frozen=True)
class ExportarPoaDelAreaCommand:
    exercise_id: int
    area_id: int
    year: int


class ExportarPoaDelArea:
    """El POA del área en el formato oficial, armado desde lo capturado.

    El árbol se sube por la acción a la que cada actividad apunta, y no por la
    versión vigente del instrumento: una actividad alineada a una versión que
    ya no es la última conserva así su eje y su línea estratégica en el papel.
    """

    def __init__(
        self,
        poa_area_repository,
        area_repository,
        strategic_tree_repository,
        unit_of_measure_repository,
        area_leadership,
    ) -> None:
        self.poa_areas = poa_area_repository
        self.areas = area_repository
        self.arbol = strategic_tree_repository
        self.unidades = unit_of_measure_repository
        self.leadership = area_leadership

    async def execute(self, command: ExportarPoaDelAreaCommand) -> PoaParaImprimir:
        poa_area = await self.poa_areas.find_poa_area(command.exercise_id, command.area_id)
        if poa_area is None:
            raise ResourceNotFoundError(EL_POA_NO_ESTA_ABIERTO)
        area = await self.areas.get_by_id(command.area_id)
        if area is None:
            raise ResourceNotFoundError(SIN_AREA)

        actividades = await self.poa_areas.list_activities(poa_area.id, include_inactive=False)
        return armar_el_poa_para_imprimir(
            area=area.name,
            responsable=await self._quien_responde(command.area_id),
            anio=command.year,
            elaborado_el=self._hoy(),
            presentado=_ya_se_presento(poa_area),
            actividades=actividades,
            nodos=await self._el_arbol_de(actividades),
            unidades=await self._las_unidades(),
        )

    async def _el_arbol_de(self, actividades: list[Activity]) -> list[StrategicNode]:
        nodos: dict[int, StrategicNode] = {}
        for node_id in {una.node_id for una in actividades if una.node_id is not None}:
            if node_id in nodos:
                continue
            try:
                accion = await self.arbol.get_by_id(node_id)
                if accion is None:
                    continue
                linaje = [*await self.arbol.ancestors(node_id), accion]
            except ResourceNotFoundError:
                continue
            for nodo in linaje:
                nodos[nodo.id] = nodo
        return list(nodos.values())

    async def _las_unidades(self) -> dict[int, tuple[str, str]]:
        return {
            unidad.id: (unidad.name, unidad.plural)
            for unidad in await self.unidades.list(active_only=False)
        }

    async def _quien_responde(self, area_id: int) -> str | None:
        return await self.leadership.person_in_charge(area_id)

    def _hoy(self) -> date:
        return institutional_today()


def _ya_se_presento(poa_area: PoaArea) -> bool:
    return poa_area.status == PoaAreaStatus.ENVIADO
