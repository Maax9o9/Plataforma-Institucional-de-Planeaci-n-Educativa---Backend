from __future__ import annotations

from dataclasses import dataclass, field

from app.shared.application.event_bus import EventBus
from app.shared.domain.exceptions import ConflictError

from ...domain.events import StrategicNodeCreated
from ...domain.pide_workbook import NodoPlaneado, PlanDeCarga
from ...domain.ports.strategic_tree_repository import StrategicTreeRepository
from ...domain.strategic_tree_entities import StrategicNode

NODO_ESTRATEGICO = "strategic_node"


class VersionConNodosError(ConflictError):
    code = "STRATEGIC_VERSION_NOT_EMPTY"
    default_message = (
        "La versión ya tiene nodos cargados. La carga del archivo sólo se permite sobre una "
        "versión vacía: cree una versión nueva y cárguela ahí."
    )


@dataclass(kw_only=True)
class ResumenDeLaCarga:
    version_id: int
    cuantos_por_nivel: dict[str, int]
    avisos: list[str] = field(default_factory=list)

    @property
    def cuantos(self) -> int:
        return sum(self.cuantos_por_nivel.values())


class LoadStrategicTreeFromPlan:
    def __init__(self, repository: StrategicTreeRepository, event_bus: EventBus) -> None:
        self.repository = repository
        self.event_bus = event_bus

    async def execute(
        self, *, version_id: int, plan: PlanDeCarga, actor_id: int | None
    ) -> ResumenDeLaCarga:
        ya_cargados = await self.repository.list_tree(version_id, include_inactive=True)
        if ya_cargados:
            raise VersionConNodosError(
                f"La versión ya tiene {len(ya_cargados)} nodos cargados. La carga del archivo "
                "sólo se permite sobre una versión vacía: cree una versión nueva y cárguela ahí."
            )

        identificadores: dict[str, int] = {}
        for planeado in plan.nodos:
            nodo = _nodo_de(planeado, version_id, identificadores)
            await self.repository.add(nodo)
            identificadores[planeado.key] = nodo.id

        resumen = ResumenDeLaCarga(
            version_id=version_id,
            cuantos_por_nivel=plan.cuantos_por_nivel(),
            avisos=list(plan.avisos),
        )
        await self.event_bus.publish(
            StrategicNodeCreated(
                actor_id=actor_id,
                aggregate_type=NODO_ESTRATEGICO,
                aggregate_id=version_id,
                action="loaded_from_workbook",
                data={"version_id": version_id, "nodos": resumen.cuantos},
            )
        )
        return resumen


def _nodo_de(
    planeado: NodoPlaneado, version_id: int, identificadores: dict[str, int]
) -> StrategicNode:
    return StrategicNode(
        version_id=version_id,
        parent_id=None if planeado.parent_key is None else identificadores[planeado.parent_key],
        kind=planeado.kind,
        key=planeado.key,
        name=planeado.name,
        order=planeado.order,
        indicator_formula=planeado.indicator_formula,
    )
