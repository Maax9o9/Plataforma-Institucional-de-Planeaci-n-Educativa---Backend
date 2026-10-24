"""Adaptador PostgreSQL del árbol de un instrumento."""

from __future__ import annotations

from typing import NoReturn

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from app.shared.domain.exceptions import InvalidStateError, ResourceNotFoundError, ValidationError
from app.shared.infrastructure.db.constraints import viola_la_restriccion

from ..domain.strategic_tree_entities import (
    NodeKind,
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
from .models import StrategicNodeModel

_UNICA_CLAVE_ENTRE_HERMANOS = "uq_nodo_estrategico_hermano_clave"
_FORANEA_DE_LA_VERSION = "fk_nodo_estrategico_version"


def _to_domain(model: StrategicNodeModel) -> StrategicNode:
    return StrategicNode(
        id=model.id,
        version_id=model.version_id,
        parent_id=model.padre_id,
        kind=NodeKind(model.tipo),
        key=model.clave,
        name=model.denominacion,
        order=model.orden,
        is_active=model.activo,
        indicator_formula=model.formula_indicador,
    )


def _raise_domain_error(exc: IntegrityError, node: StrategicNode) -> NoReturn:
    """Traduce sólo las restricciones que el repositorio sabe explicar.

    Un `IntegrityError` también sale de un NOT NULL o de otra foránea: decir
    «clave repetida» cuando falló otra cosa manda a buscar un duplicado que no
    está. Las demás se levantan tal cual.
    """
    if viola_la_restriccion(exc, _UNICA_CLAVE_ENTRE_HERMANOS):
        raise repeated_key_error(node) from exc
    if viola_la_restriccion(exc, _FORANEA_DE_LA_VERSION):
        raise ValidationError("La versión del instrumento no existe.") from exc
    raise exc


class SqlAlchemyStrategicTreeRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def list_tree(
        self, version_id: int, *, include_inactive: bool = False
    ) -> list[StrategicNode]:
        async with self.session_factory() as session:
            models = (
                await session.scalars(
                    select(StrategicNodeModel).where(StrategicNodeModel.version_id == version_id)
                )
            ).all()
        # Se recorre el árbol entero y se filtra después: filtrar antes dejaría
        # sin padre al nodo activo de uno retirado.
        return [
            node
            for node in in_traversal_order(_to_domain(model) for model in models)
            if include_inactive or node.is_active
        ]

    async def get_by_id(self, node_id: int) -> StrategicNode | None:
        async with self.session_factory() as session:
            model = await session.get(StrategicNodeModel, node_id)
            return _to_domain(model) if model is not None else None

    async def add(self, node: StrategicNode) -> None:
        node.validate()
        async with self.session_factory() as session:
            upward = await self._upward(session, node.parent_id)
            ensure_parent_fits(node, upward)
            padre = upward[0] if upward else None
            ensure_kind_fits_under(node, padre)
            ensure_parent_is_active(node, padre)
            model = StrategicNodeModel(
                version_id=node.version_id,
                padre_id=node.parent_id,
                tipo=node.kind.value,
                clave=node.key,
                denominacion=node.name,
                orden=node.order,
                activo=node.is_active,
                formula_indicador=node.indicator_formula,
            )
            session.add(model)
            try:
                await session.flush()
            except IntegrityError as exc:
                await session.rollback()
                _raise_domain_error(exc, node)
            new_id = model.id
            await session.commit()
        node.id = new_id

    async def update(self, node: StrategicNode) -> None:
        """Las reglas, en el mismo orden que en el adaptador en memoria: el
        padre, el ciclo, el nivel hacia arriba, el padre retirado, el nivel
        hacia abajo, lo que cuelga y la clave -esta última la impone la base-.
        El orden decide qué mensaje sale cuando una operación rompe más de una
        regla, y los dos adaptadores tienen que dar el mismo.

        Las dos reglas que miran hacia abajo cuestan una consulta por `padre_id`
        y sólo se pagan cuando el nivel cambia o el nodo se retira, que es
        cuando lo que cuelga de él puede quedar mal.
        """
        node.validate()
        async with self.session_factory() as session:
            model = await session.get(StrategicNodeModel, node.id)
            if model is None:
                raise ResourceNotFoundError("El nodo no existe.")
            if node.version_id != model.version_id:
                raise ValidationError("Un nodo no cambia de versión.")
            estaba_activo, nivel_de_antes, padre_de_antes = (
                model.activo,
                NodeKind(model.tipo),
                model.padre_id,
            )
            upward = await self._upward(session, node.parent_id)
            ensure_parent_fits(node, upward)
            ensure_no_cycle(node, upward)
            padre = upward[0] if upward else None
            ensure_kind_fits_under(node, padre)
            if node.parent_id != padre_de_antes or (node.is_active and not estaba_activo):
                ensure_parent_is_active(node, padre)
            if node.kind is not nivel_de_antes:
                ensure_children_stay_deeper(node, await self._children_of(session, node.id))
            if estaba_activo and not node.is_active:
                ensure_nothing_active_hangs(node, await self._children_of(session, node.id))
            model.padre_id = node.parent_id
            model.tipo = node.kind.value
            model.clave = node.key
            model.denominacion = node.name
            model.orden = node.order
            model.activo = node.is_active
            model.formula_indicador = node.indicator_formula
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                _raise_domain_error(exc, node)

    async def deactivate(self, node_id: int) -> None:
        async with self.session_factory() as session:
            result = await session.execute(
                update(StrategicNodeModel)
                .where(StrategicNodeModel.id == node_id)
                .values(activo=False)
            )
            if result.rowcount != 1:
                raise ResourceNotFoundError("El nodo no existe.")
            await session.commit()

    async def ancestors(self, node_id: int) -> list[StrategicNode]:
        async with self.session_factory() as session:
            upward = await self._upward(session, node_id)
        if not upward:
            raise ResourceNotFoundError("El nodo no existe.")
        # `upward` empieza en el propio nodo y sube hasta el eje.
        return list(reversed(upward[1:]))

    async def _children_of(self, session: AsyncSession, node_id: int) -> list[StrategicNode]:
        """Los que cuelgan del nodo, retirados incluidos.

        Es la consulta que la regla de nivel obliga a hacer: mirar sólo al padre
        deja que un nodo con hijos cambie de nivel y los deje por encima de él.
        """
        models = (
            await session.scalars(
                select(StrategicNodeModel).where(StrategicNodeModel.padre_id == node_id)
            )
        ).all()
        return [_to_domain(model) for model in models]

    async def _upward(self, session: AsyncSession, start_id: int | None) -> list[StrategicNode]:
        """`start_id` y sus ancestros, del más cercano al más lejano; vacía si
        no existe.

        Es una consulta, no un cálculo sobre la clave. La clave de un nodo la
        fija el documento fuente («E1.L2.A3») y puede no contener ni rastro de
        la de su padre: partirla encuentra nodos que no son o no encuentra nada.
        El padre está en `padre_id`, y subir por él es lo que hace esta
        `WITH RECURSIVE`, la primera de `app/`. La primera del repositorio la
        dejó la tarea 1, en `tests/test_arbol_del_pide_migracion.py`.

        Es `UNION` y no `UNION ALL` a propósito. La base acepta un ciclo -la
        foránea compuesta sólo exige que el padre exista en la misma versión-, y
        sobre uno un recursivo con `UNION ALL` no termina nunca. Con `UNION`
        cada nodo entra una sola vez, así que la subida termina aunque el árbol
        esté mal; el ciclo se descubre al ordenar el resultado y se dice en vez
        de colgar la petición. El repositorio no deja crear ciclos -`update` lo
        revisa antes de escribir-: esto es para cuando alguien los escriba por
        fuera.

        **No agregue columnas a este `SELECT`.** Lo que hace terminar la
        consulta es que `UNION` deduplique filas, y eso sólo funciona mientras
        las filas sean `(id, padre_id)`: con una columna de distancia cada
        vuelta del ciclo produce una fila distinta, `UNION` deja de deduplicar
        y la consulta no termina. Medido sobre un ciclo escrito a mano: tal
        como está termina en 1 ms; con la columna de distancia muere por
        `statement_timeout` a los 2 s. Un tope de profundidad tampoco es la
        salida -sobre un ciclo con `UNION` es inalcanzable, y sobre una cadena
        legítima la truncaría en silencio: una de 5 000 niveles devuelve los
        4 999 en 0.64 s-.
        """
        if start_id is None:
            return []

        ascent = (
            select(StrategicNodeModel.id, StrategicNodeModel.padre_id)
            .where(StrategicNodeModel.id == start_id)
            .cte("ascenso", recursive=True)
        )
        parent = aliased(StrategicNodeModel)
        ascent = ascent.union(
            select(parent.id, parent.padre_id).join(ascent, parent.id == ascent.c.padre_id)
        )
        models = (
            await session.scalars(
                select(StrategicNodeModel).join(ascent, StrategicNodeModel.id == ascent.c.id)
            )
        ).all()

        # La consulta devuelve el conjunto sin orden: se ordena subiendo por el
        # padre desde el nodo, que de paso delata el ciclo.
        by_id = {model.id: model for model in models}
        chain: list[StrategicNode] = []
        visited: set[int] = set()
        current = by_id.get(start_id)
        while current is not None:
            if current.id in visited:
                raise InvalidStateError(
                    f"El árbol tiene un ciclo: el nodo {current.id} es su propio ancestro."
                )
            visited.add(current.id)
            chain.append(_to_domain(current))
            current = by_id.get(current.padre_id)
        return chain
