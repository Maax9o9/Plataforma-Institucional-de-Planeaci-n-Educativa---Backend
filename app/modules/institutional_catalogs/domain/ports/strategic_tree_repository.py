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

    El nivel del hijo va estrictamente más abajo que el del padre, en el orden
    `eje → objetivo_general → objetivo_especifico → linea_estrategica →
    accion`. Saltarse niveles vale -el documento fuente los salta-; repetir o
    subir, no. La regla se mira al dar de alta, al mudar y al cambiar el nivel
    de un nodo que ya tiene hijos.

    Errores: `ValidationError` si el nivel, la clave o la denominación no valen,
    si el padre no existe, es de otra versión o no va más arriba en la cadena de
    niveles, si el nodo se mudaría bajo uno de sus descendientes, si cambiaría de
    versión o si al cambiar de nivel dejaría a sus hijos por encima de él;
    `ConflictError` si un hermano ya
    tiene esa clave; `ResourceNotFoundError` si el nodo que se actualiza, se
    desactiva o se consulta por sus ancestros no existe; `InvalidStateError` si
    el árbol guardado tiene un ciclo -`list_tree` y `ancestors`-.
    """

    async def list_tree(
        self, version_id: int, *, include_inactive: bool = False
    ) -> list[StrategicNode]:
        """Los nodos de la versión en orden de recorrido.

        Por omisión sin los desactivados: quien formula no debe ver nodos
        retirados. Un nodo activo cuyo padre está desactivado sí aparece, en el
        lugar que le toca -y su `parent_id` apunta entonces a un nodo que no
        está en la lista-: retirar un nodo no afecta a lo que cuelga de él.

        Lo que no se alcanza no se omite: si algún nodo de la versión no cuelga
        de ninguna raíz -un ciclo escrito por fuera- levanta `InvalidStateError`
        diciendo cuántos y cuáles. Un nodo que existe y no aparece es lo peor
        que le puede pasar a un sistema que acredita cifras ante una revisión
        externa.
        """
        ...

    async def get_by_id(self, node_id: int) -> StrategicNode | None: ...

    async def add(self, node: StrategicNode) -> None:
        """Guarda el nodo y le asigna su `id`."""
        ...

    async def update(self, node: StrategicNode) -> None:
        """Reemplaza lo editable del nodo `node.id`: nivel, clave, denominación,
        orden, padre y si está activo. La versión no cambia."""
        ...

    async def deactivate(self, node_id: int) -> None:
        """Retira el nodo sin tocar lo que cuelga de él. Retirar uno ya retirado
        no es un error."""
        ...

    async def ancestors(self, node_id: int) -> list[StrategicNode]:
        """Los ancestros del nodo, del eje hacia abajo y sin incluir al nodo.
        Cuentan los desactivados: son la historia de adónde pertenece."""
        ...
