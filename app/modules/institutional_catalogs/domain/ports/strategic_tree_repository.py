"""Puerto del árbol de un instrumento."""

from __future__ import annotations

from typing import Protocol

from ..strategic_tree_entities import StrategicNode


class StrategicTreeRepository(Protocol):
    """Los nodos de las versiones de un instrumento.

    No hay borrado: un nodo que ya se usa deja de poder borrarse, y lo que
    cuelga de él -otros nodos, indicadores, las actividades de un área-
    dejaría de saber a qué respondía. Se desactiva, y el desactivado sigue
    siendo legible.
    """

    async def list_tree(
        self, version_id: int, *, include_inactive: bool = False
    ) -> list[StrategicNode]:
        """Los nodos de la versión en orden de recorrido.

        Por omisión sin los desactivados: quien formula no debe ver nodos
        retirados. Un nodo activo cuyo padre está desactivado sí aparece, en el
        lugar que le toca: retirar un nodo no afecta a lo que cuelga de él.
        """
        ...

    async def get_by_id(self, node_id: int) -> StrategicNode | None: ...

    async def add(self, node: StrategicNode) -> None:
        """Guarda el nodo y le asigna su `id`."""
        ...

    async def update(self, node: StrategicNode) -> None: ...

    async def deactivate(self, node_id: int) -> None:
        """Retira el nodo sin tocar lo que cuelga de él. Retirar uno ya retirado
        no es un error."""
        ...

    async def ancestors(self, node_id: int) -> list[StrategicNode]:
        """Los ancestros del nodo, del eje hacia abajo y sin incluir al nodo.
        Cuentan los desactivados: son la historia de adónde pertenece."""
        ...
