from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Path, Query, Request, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.concurrency import run_in_threadpool

from app.core.error_responses import los_errores_que_devuelve
from app.core.security import get_current_user, require_roles
from app.shared.domain.exceptions import PayloadTooLargeError

from ..application.use_cases.load_strategic_tree import (
    LoadStrategicTreeFromPlan,
    VersionConNodosError,
)
from ..application.use_cases.manage_strategic_tree import (
    CreateStrategicNode,
    DeactivateStrategicNode,
    UpdateStrategicNode,
)
from ..domain.entities import InstrumentVersion
from ..domain.pide_workbook import WorkbookShapeError, plan_de_carga
from ..domain.strategic_tree_entities import (
    MAYOR_ENTERO_DE_LA_BASE,
    MENOR_ENTERO_DE_LA_BASE,
    ActiveChildrenError,
    NodeKind,
    RepeatedKeyError,
    StrategicNode,
)
from ..infrastructure.pide_workbook_reader import filas_del_libro

router = APIRouter(prefix="/pide", tags=["Catalogo del PIDE"])

IdEnLaRuta = Annotated[int, Path(ge=1, le=MAYOR_ENTERO_DE_LA_BASE)]
IdEnElFiltro = Annotated[int | None, Query(ge=1, le=MAYOR_ENTERO_DE_LA_BASE)]
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

    tipo: NodeKind
    clave: str
    denominacion: str
    orden: Orden
    padre_id: IdDeNodo | None = None
    formula_indicador: str | None = None


class ActualizarNodoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: NodeKind | None = None
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


class VersionRespuesta(BaseModel):
    id: int
    instrumento_id: int
    etiqueta: str
    vigente_desde: date
    publicada_en: datetime | None
    origen: str | None

    @classmethod
    def from_domain(cls, version: InstrumentVersion) -> VersionRespuesta:
        return cls(
            id=version.id,
            instrumento_id=version.instrument_id,
            etiqueta=version.label,
            vigente_desde=version.effective_from,
            publicada_en=version.published_at,
            origen=version.origin,
        )


@router.get(
    "/versiones",
    response_model=list[VersionRespuesta],
    summary="Consultar las versiones de los instrumentos",
)
async def list_versions(
    request: Request,
    instrumento_id: IdEnElFiltro = None,
    _user=Depends(get_current_user),
) -> list[VersionRespuesta]:
    versiones = await request.app.state.instrument_version_repository.list(
        instrument_id=instrumento_id
    )
    return [VersionRespuesta.from_domain(version) for version in versiones]


class NodoRespuesta(BaseModel):
    id: int
    version_id: int
    padre_id: int | None
    tipo: NodeKind
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
    responses=los_errores_que_devuelve(RepeatedKeyError),
)
async def create_node(
    version_id: IdEnLaRuta,
    body: CrearNodoRequest,
    request: Request,
    usuario=Depends(requires_write_role),
) -> NodoRespuesta:
    node = await CreateStrategicNode(
        request.app.state.strategic_tree_repository, request.app.state.event_bus
    ).execute(
        version_id=version_id,
        parent_id=body.padre_id,
        kind=body.tipo,
        key=body.clave,
        name=body.denominacion,
        order=body.orden,
        indicator_formula=body.formula_indicador,
        actor_id=usuario.id,
    )
    return NodoRespuesta.from_domain(node)


@router.patch(
    "/nodos/{nodo_id}",
    response_model=NodoRespuesta,
    summary="Corregir un nodo del arbol",
    responses=los_errores_que_devuelve(RepeatedKeyError, ActiveChildrenError),
)
async def update_node(
    nodo_id: IdEnLaRuta,
    body: ActualizarNodoRequest,
    request: Request,
    usuario=Depends(requires_write_role),
) -> NodoRespuesta:
    node = await UpdateStrategicNode(
        request.app.state.strategic_tree_repository, request.app.state.event_bus
    ).execute(nodo_id, body.node_changes_from_sent_fields(), actor_id=usuario.id)
    return NodoRespuesta.from_domain(node)


@router.post(
    "/nodos/{nodo_id}/desactivar",
    response_model=NodoRespuesta,
    summary="Retirar un nodo del arbol",
    responses=los_errores_que_devuelve(ActiveChildrenError),
)
async def deactivate_node(
    nodo_id: IdEnLaRuta,
    request: Request,
    usuario=Depends(requires_write_role),
) -> NodoRespuesta:
    node = await DeactivateStrategicNode(
        request.app.state.strategic_tree_repository, request.app.state.event_bus
    ).execute(nodo_id, actor_id=usuario.id)
    return NodoRespuesta.from_domain(node)


class CargaDelPideRespuesta(BaseModel):
    version_id: int
    aplicada: bool
    cuantos: int
    por_nivel: dict[str, int]
    avisos: list[str]


@router.post(
    "/versiones/{version_id}/carga",
    response_model=CargaDelPideRespuesta,
    summary="Cargar el arbol de una version desde el libro de Excel acordado",
    responses=los_errores_que_devuelve(WorkbookShapeError, VersionConNodosError),
)
async def load_tree_from_workbook(
    version_id: IdEnLaRuta,
    request: Request,
    archivo: UploadFile = File(...),
    solo_revisar: bool = Query(default=False),
    usuario=Depends(requires_write_role),
) -> CargaDelPideRespuesta:
    limite = request.app.state.settings.upload_max_bytes
    contenido = await archivo.read(limite + 1)
    if len(contenido) > limite:
        raise PayloadTooLargeError(details={"max_bytes": limite})

    filas_de_acciones, filas_de_objetivos = await run_in_threadpool(filas_del_libro, contenido)
    plan = await run_in_threadpool(plan_de_carga, filas_de_acciones, filas_de_objetivos)

    repositorio = request.app.state.strategic_tree_repository
    if solo_revisar:
        ya_cargados = await repositorio.list_tree(version_id, include_inactive=True)
        avisos = list(plan.avisos)
        if ya_cargados:
            avisos.insert(
                0,
                f"La versión ya tiene {len(ya_cargados)} nodos: la carga se rechazará hasta "
                "que elija una versión vacía.",
            )
        return CargaDelPideRespuesta(
            version_id=version_id,
            aplicada=False,
            cuantos=len(plan.nodos),
            por_nivel=plan.cuantos_por_nivel(),
            avisos=avisos,
        )

    resumen = await LoadStrategicTreeFromPlan(repositorio, request.app.state.event_bus).execute(
        version_id=version_id, plan=plan, actor_id=usuario.id
    )
    return CargaDelPideRespuesta(
        version_id=resumen.version_id,
        aplicada=True,
        cuantos=resumen.cuantos,
        por_nivel=resumen.cuantos_por_nivel,
        avisos=resumen.avisos,
    )
