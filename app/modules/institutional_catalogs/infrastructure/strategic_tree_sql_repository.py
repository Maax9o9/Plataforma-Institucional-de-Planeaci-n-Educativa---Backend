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
    cabe_en_el_entero_de_la_base,
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
        if not cabe_en_el_entero_de_la_base(version_id):
            return []
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
        if not cabe_en_el_entero_de_la_base(node_id):
            return None
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
        node.validate()
        if not cabe_en_el_entero_de_la_base(node.id):
            raise ResourceNotFoundError("El nodo no existe.")
        async with self.session_factory() as session:
            model = await session.get(StrategicNodeModel, node.id)
            if model is None:
                raise ResourceNotFoundError("El nodo no existe.")
            if node.version_id != model.version_id:
                raise ValidationError("Un nodo no cambia de versión.")
            se_cuelga_de_otro_padre = node.parent_id != model.padre_id
            vuelve_a_estar_activo = node.is_active and not model.activo
            cambia_de_nivel = node.kind is not NodeKind(model.tipo)
            se_retira = model.activo and not node.is_active
            upward = await self._upward(session, node.parent_id)
            ensure_parent_fits(node, upward)
            ensure_no_cycle(node, upward)
            padre = upward[0] if upward else None
            ensure_kind_fits_under(node, padre)
            if se_cuelga_de_otro_padre or vuelve_a_estar_activo:
                ensure_parent_is_active(node, padre)
            if cambia_de_nivel:
                ensure_children_stay_deeper(node, await self._children_of(session, node.id))
            if se_retira:
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
        if not cabe_en_el_entero_de_la_base(node_id):
            raise ResourceNotFoundError("El nodo no existe.")
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
        if not cabe_en_el_entero_de_la_base(node_id):
            raise ResourceNotFoundError("El nodo no existe.")
        async with self.session_factory() as session:
            desde_el_nodo_hasta_el_eje = await self._upward(session, node_id)
        if not desde_el_nodo_hasta_el_eje:
            raise ResourceNotFoundError("El nodo no existe.")
        return list(reversed(desde_el_nodo_hasta_el_eje[1:]))

    async def _children_of(self, session: AsyncSession, node_id: int) -> list[StrategicNode]:
        models = (
            await session.scalars(
                select(StrategicNodeModel).where(StrategicNodeModel.padre_id == node_id)
            )
        ).all()
        return [_to_domain(model) for model in models]

    async def _upward(self, session: AsyncSession, start_id: int | None) -> list[StrategicNode]:
        if start_id is None:
            return []

        ascenso_sin_filas_repetidas = (
            select(StrategicNodeModel.id, StrategicNodeModel.padre_id)
            .where(StrategicNodeModel.id == start_id)
            .cte("ascenso", recursive=True)
        )
        parent = aliased(StrategicNodeModel)
        ascenso_sin_filas_repetidas = ascenso_sin_filas_repetidas.union(
            select(parent.id, parent.padre_id).join(
                ascenso_sin_filas_repetidas,
                parent.id == ascenso_sin_filas_repetidas.c.padre_id,
            )
        )
        models = (
            await session.scalars(
                select(StrategicNodeModel).join(
                    ascenso_sin_filas_repetidas,
                    StrategicNodeModel.id == ascenso_sin_filas_repetidas.c.id,
                )
            )
        ).all()

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
