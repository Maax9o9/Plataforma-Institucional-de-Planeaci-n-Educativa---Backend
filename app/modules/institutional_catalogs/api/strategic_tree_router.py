from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.security import get_current_user, require_roles

from ..application.use_cases.manage_strategic_tree import (
    CreateStrategicNode,
    DeactivateStrategicNode,
    UpdateStrategicNode,
)
from ..domain.strategic_tree_entities import (
    MAYOR_ENTERO_DE_LA_BASE,
    MENOR_ENTERO_DE_LA_BASE,
    StrategicNode,
)

router = APIRouter(prefix="/pide", tags=["Catalogo del PIDE"])

IdEnLaRuta = Annotated[int, Path(ge=1, le=MAYOR_ENTERO_DE_LA_BASE)]
IdDeNodo = Annotated[int, Field(ge=1, le=MAYOR_ENTERO_DE_LA_BASE)]
Orden = Annotated[int, Field(ge=MENOR_ENTERO_DE_LA_BASE, le=MAYOR_ENTERO_DE_LA_BASE)]

ATTRIBUTE_OF_FIELD = {
    "tipo": "kind",
    "clave": "key",
    "denominacion": "name",
    "orden": "order",
    "padre_id": "parent_id",
    "activo": "is_active",
    "formula_indicador": "indicator_formula",
}

requires_write_role = require_roles("planeacion", "admin_sistema")


class CrearNodoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: str
    clave: str
    denominacion: str
    orden: Orden
    padre_id: IdDeNodo | None = None
    formula_indicador: str | None = None


class ActualizarNodoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: str | None = None
    clave: str | None = None
    denominacion: str | None = None
    orden: Orden | None = None
    padre_id: IdDeNodo | None = None
    activo: bool | None = None
    formula_indicador: str | None = None

    @field_validator("tipo", "clave", "denominacion", "orden", "activo")
    @classmethod
    def reject_explicit_null(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("Este campo no admite nulo: omítalo para dejarlo como está.")
        return value

    def node_changes_from_sent_fields(self) -> dict[str, Any]:
        return {
            ATTRIBUTE_OF_FIELD[field]: value
            for field, value in self.model_dump(exclude_unset=True).items()
        }


class NodoRespuesta(BaseModel):
    id: int
    version_id: int
    padre_id: int | None
    tipo: str
    clave: str
    denominacion: str
    orden: int
    activo: bool
    formula_indicador: str | None

    @classmethod
    def from_domain(cls, node: StrategicNode) -> NodoRespuesta:
        return cls(
            id=node.id,
            version_id=node.version_id,
            padre_id=node.parent_id,
            tipo=node.kind.value,
            clave=node.key,
            denominacion=node.name,
            orden=node.order,
            activo=node.is_active,
            formula_indicador=node.indicator_formula,
        )


@router.get(
    "/versiones/{version_id}/nodos",
    response_model=list[NodoRespuesta],
    summary="Consultar el arbol de una version del instrumento",
)
async def list_nodes(
    version_id: IdEnLaRuta,
    request: Request,
    incluir_inactivos: bool = Query(default=False),
    _user=Depends(get_current_user),
) -> list[NodoRespuesta]:
    nodes = await request.app.state.strategic_tree_repository.list_tree(
        version_id, include_inactive=incluir_inactivos
    )
    return [NodoRespuesta.from_domain(node) for node in nodes]


@router.post(
    "/versiones/{version_id}/nodos",
    response_model=NodoRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar un nodo del arbol",
)
async def create_node(
    version_id: IdEnLaRuta,
    body: CrearNodoRequest,
    request: Request,
    _user=Depends(requires_write_role),
) -> NodoRespuesta:
    node = await CreateStrategicNode(request.app.state.strategic_tree_repository).execute(
        version_id=version_id,
        parent_id=body.padre_id,
        kind=body.tipo,
        key=body.clave,
        name=body.denominacion,
        order=body.orden,
        indicator_formula=body.formula_indicador,
    )
    return NodoRespuesta.from_domain(node)


@router.patch(
    "/nodos/{nodo_id}",
    response_model=NodoRespuesta,
    summary="Corregir un nodo del arbol",
)
async def update_node(
    nodo_id: IdEnLaRuta,
    body: ActualizarNodoRequest,
    request: Request,
    _user=Depends(requires_write_role),
) -> NodoRespuesta:
    node = await UpdateStrategicNode(request.app.state.strategic_tree_repository).execute(
        nodo_id, body.node_changes_from_sent_fields()
    )
    return NodoRespuesta.from_domain(node)


@router.post(
    "/nodos/{nodo_id}/desactivar",
    response_model=NodoRespuesta,
    summary="Retirar un nodo del arbol",
)
async def deactivate_node(
    nodo_id: IdEnLaRuta,
    request: Request,
    _user=Depends(requires_write_role),
) -> NodoRespuesta:
    node = await DeactivateStrategicNode(request.app.state.strategic_tree_repository).execute(
        nodo_id
    )
    return NodoRespuesta.from_domain(node)
