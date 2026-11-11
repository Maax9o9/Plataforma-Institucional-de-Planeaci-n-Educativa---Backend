"""Repositorio en memoria del árbol de un instrumento."""

from __future__ import annotations

from dataclasses import replace
from itertools import count

from app.shared.domain.exceptions import ResourceNotFoundError, ValidationError

from ..domain.strategic_tree_entities import (
    StrategicNode,
    ensure_children_stay_deeper,
    ensure_kind_fits_under,
    ensure_no_cycle,
    ensure_nothing_active_hangs,
    ensure_parent_fits,
    ensure_parent_is_active,
    in_traversal_order,
    repeated_key_error,
)


class InMemoryStrategicTreeRepository:
    """Guarda copias y entrega copias, como una base entrega filas nuevas: quien
    toca un nodo que le dieron no cambia el árbol sin pasar por `update`.

    No tiene tabla de versiones, así que no sabe si una `version_id` existe: en
    PostgreSQL una versión inexistente la rechaza la foránea.
    """

    def __init__(self) -> None:
        self._next_id = count(1)
        self._nodes: dict[int, StrategicNode] = {}

    async def list_tree(
        self, version_id: int, *, include_inactive: bool = False
    ) -> list[StrategicNode]:
        # Se recorre el árbol entero y se filtra después: filtrar antes dejaría
        # sin padre al nodo activo de uno retirado.
        version = [node for node in self._nodes.values() if node.version_id == version_id]
        return [
            replace(node)
            for node in in_traversal_order(version)
            if include_inactive or node.is_active
        ]

    async def get_by_id(self, node_id: int) -> StrategicNode | None:
        node = self._nodes.get(node_id)
        return replace(node) if node is not None else None

    async def add(self, node: StrategicNode) -> None:
        node.validate()
        upward = self._upward(node.parent_id)
        ensure_parent_fits(node, upward)
        padre = upward[0] if upward else None
        ensure_kind_fits_under(node, padre)
        ensure_parent_is_active(node, padre)
        self._ensure_key_is_free(node, ignoring=None)
        node.id = next(self._next_id)
        self._nodes[node.id] = replace(node)

    async def update(self, node: StrategicNode) -> None:
        node.validate()
        current = self._nodes.get(node.id)
        if current is None:
            raise ResourceNotFoundError("El nodo no existe.")
        if node.version_id != current.version_id:
            raise ValidationError("Un nodo no cambia de versión.")
        upward = self._upward(node.parent_id)
        ensure_parent_fits(node, upward)
        ensure_no_cycle(node, upward)
        padre = upward[0] if upward else None
        ensure_kind_fits_under(node, padre)
        se_cuelga_de_otro_padre = node.parent_id != current.parent_id
        vuelve_a_estar_activo = node.is_active and not current.is_active
        cambia_de_nivel = node.kind is not current.kind
        se_retira = current.is_active and not node.is_active
        if se_cuelga_de_otro_padre or vuelve_a_estar_activo:
            ensure_parent_is_active(node, padre)
        if cambia_de_nivel:
            ensure_children_stay_deeper(node, self._children_of(node.id))
        if se_retira:
            ensure_nothing_active_hangs(node, self._children_of(node.id))
        self._ensure_key_is_free(node, ignoring=node.id)
        self._nodes[node.id] = replace(node)

    async def deactivate(self, node_id: int) -> None:
        node = self._nodes.get(node_id)
        if node is None:
            raise ResourceNotFoundError("El nodo no existe.")
        if node.is_active:
            ensure_nothing_active_hangs(node, self._children_of(node_id))
        node.is_active = False

    async def ancestors(self, node_id: int) -> list[StrategicNode]:
        if node_id not in self._nodes:
            raise ResourceNotFoundError("El nodo no existe.")
        upward = self._upward(self._nodes[node_id].parent_id)
        return [replace(node) for node in reversed(upward)]

    def _upward(self, start_id: int | None) -> list[StrategicNode]:
        """`start_id` y sus ancestros, del más cercano al más lejano; vacía si no
        existe. El árbol se sube por `parent_id`, nunca partiendo la clave."""
        chain: list[StrategicNode] = []
        current = self._nodes.get(start_id) if start_id is not None else None
        while current is not None:
            chain.append(current)
            current = self._nodes.get(current.parent_id) if current.parent_id is not None else None
        return chain

    def _children_of(self, node_id: int) -> list[StrategicNode]:
        return [node for node in self._nodes.values() if node.parent_id == node_id]

    def _ensure_key_is_free(self, node: StrategicNode, *, ignoring: int | None) -> None:
        """La `UNIQUE (version_id, padre_id, clave)` de la base. `None == None`
        aquí: los ejes son hermanos entre sí, y es lo que `NULLS NOT DISTINCT`
        hace en PostgreSQL. `ignoring` es el nodo que se está actualizando: no
        choca consigo mismo."""
        for other in self._nodes.values():
            if (
                other.id != ignoring
                and other.version_id == node.version_id
                and other.parent_id == node.parent_id
                and other.key == node.key
            ):
                raise repeated_key_error(node)
