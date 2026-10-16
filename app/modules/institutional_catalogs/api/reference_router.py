"""Endpoints de tipos de indicador."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, Field

from app.core.security import get_current_user, require_roles

from ..application.use_cases.manage_reference import DeactivateReference, UpdateReference
from ..application.use_cases.manage_unit_of_measure import (
    CreateUnitOfMeasure,
    DeactivateUnitOfMeasure,
    UpdateUnitOfMeasure,
)
from ..domain.reference_entities import ReferenceItem
from ..domain.unit_of_measure_entities import UnitOfMeasure

router = APIRouter(prefix="/catalogos", tags=["Catalogos institucionales"])


class CrearReferenciaRequest(BaseModel):
    clave: str = Field(min_length=1, max_length=50)
    nombre: str = Field(min_length=1, max_length=300)
    version: int | None = Field(default=None, ge=1)


class ReferenciaRespuesta(BaseModel):
    id: int
    clave: str
    nombre: str
    activo: bool
    version: int

    @classmethod
    def from_domain(cls, item: ReferenceItem) -> ReferenciaRespuesta:
        return cls(
            id=item.id,
            clave=item.key,
            nombre=item.name,
            activo=item.is_active,
            version=item.version,
        )


async def _list(
    request: Request,
    state_name: str,
    user,
    activo: bool | None,
) -> list[ReferenciaRespuesta]:
    items = await getattr(request.app.state, state_name).list()
    if activo is not None:
        items = [item for item in items if item.is_active is activo]
    return [ReferenciaRespuesta.from_domain(item) for item in items]


async def _create(request: Request, state_name: str, body: CrearReferenciaRequest) -> ReferenceItem:
    item = ReferenceItem.create(key=body.clave, name=body.nombre)
    await getattr(request.app.state, state_name).add(item)
    return item


@router.get(
    "/criterios-seaes",
    response_model=list[ReferenciaRespuesta],
    summary="Consultar criterios SEAES",
)
async def list_criteria(
    request: Request,
    activo: bool | None = Query(default=True),
    _user=Depends(get_current_user),
):
    return await _list(request, "criteria_repository", _user, activo)


@router.post(
    "/criterios-seaes",
    response_model=ReferenciaRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar criterio SEAES",
)
async def create_criteria(
    body: CrearReferenciaRequest,
    request: Request,
    _user=Depends(require_roles("planeacion", "admin_sistema")),
):
    return ReferenciaRespuesta.from_domain(await _create(request, "criteria_repository", body))


@router.patch(
    "/criterios-seaes/{item_id}",
    response_model=ReferenciaRespuesta,
    summary="Editar criterio SEAES",
)
async def update_criteria(
    item_id: int,
    body: CrearReferenciaRequest,
    request: Request,
    current_user=Depends(require_roles("planeacion", "admin_sistema")),
):
    item = await UpdateReference(
        request.app.state.criteria_repository,
        request.app.state.event_bus,
    ).execute(item_id, body.clave, body.nombre, current_user.id, body.version)
    return ReferenciaRespuesta.from_domain(item)


@router.post(
    "/criterios-seaes/{item_id}/desactivar",
    response_model=ReferenciaRespuesta,
    summary="Desactivar criterio SEAES",
)
async def deactivate_criteria(
    item_id: int,
    request: Request,
    version: int | None = Query(default=None, ge=1),
    current_user=Depends(require_roles("planeacion", "admin_sistema")),
):
    item = await DeactivateReference(
        request.app.state.criteria_repository,
        request.app.state.event_bus,
    ).execute(item_id, current_user.id, version)
    return ReferenciaRespuesta.from_domain(item)


@router.get(
    "/tipos-indicador",
    response_model=list[ReferenciaRespuesta],
    summary="Consultar tipos de indicador",
)
async def list_indicator_types(
    request: Request,
    activo: bool | None = Query(default=True),
    _user=Depends(get_current_user),
):
    return await _list(request, "indicator_type_repository", _user, activo)


@router.post(
    "/tipos-indicador",
    response_model=ReferenciaRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar tipo de indicador",
)
async def create_indicator_type(
    body: CrearReferenciaRequest,
    request: Request,
    _user=Depends(require_roles("planeacion", "admin_sistema")),
):
    return ReferenciaRespuesta.from_domain(
        await _create(request, "indicator_type_repository", body)
    )


@router.patch(
    "/tipos-indicador/{item_id}",
    response_model=ReferenciaRespuesta,
    summary="Editar tipo de indicador",
)
async def update_indicator_type(
    item_id: int,
    body: CrearReferenciaRequest,
    request: Request,
    current_user=Depends(require_roles("planeacion", "admin_sistema")),
):
    item = await UpdateReference(
        request.app.state.indicator_type_repository,
        request.app.state.event_bus,
    ).execute(item_id, body.clave, body.nombre, current_user.id, body.version)
    return ReferenciaRespuesta.from_domain(item)


@router.post(
    "/tipos-indicador/{item_id}/desactivar",
    response_model=ReferenciaRespuesta,
    summary="Desactivar tipo de indicador",
)
async def deactivate_indicator_type(
    item_id: int,
    request: Request,
    version: int | None = Query(default=None, ge=1),
    current_user=Depends(require_roles("planeacion", "admin_sistema")),
):
    item = await DeactivateReference(
        request.app.state.indicator_type_repository,
        request.app.state.event_bus,
    ).execute(item_id, current_user.id, version)
    return ReferenciaRespuesta.from_domain(item)


class CrearUnidadMedidaRequest(BaseModel):
    clave: str = Field(min_length=1, max_length=50)
    nombre: str = Field(min_length=1, max_length=100)
    plural: str = Field(min_length=1, max_length=100)
    version: int | None = Field(default=None, ge=1)


class UnidadMedidaRespuesta(BaseModel):
    id: int
    clave: str
    nombre: str
    plural: str
    activo: bool
    version: int

    @classmethod
    def from_domain(cls, item: UnitOfMeasure) -> UnidadMedidaRespuesta:
        return cls(
            id=item.id,
            clave=item.key,
            nombre=item.name,
            plural=item.plural,
            activo=item.is_active,
            version=item.version,
        )


@router.get(
    "/unidades-medida",
    response_model=list[UnidadMedidaRespuesta],
    summary="Consultar unidades de medida",
)
async def list_units_of_measure(
    request: Request,
    activo: bool | None = Query(default=True),
    _user=Depends(get_current_user),
):
    # A diferencia de `_list`, aqui se trae el catalogo completo y se filtra
    # despues: la actividad puede necesitar ver una unidad ya desactivada
    # (`?activo=false`) para no perder lo que ya tenia guardado como texto.
    items = await request.app.state.unit_of_measure_repository.list(active_only=False)
    if activo is not None:
        items = [item for item in items if item.is_active is activo]
    return [UnidadMedidaRespuesta.from_domain(item) for item in items]


@router.post(
    "/unidades-medida",
    response_model=UnidadMedidaRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar unidad de medida",
)
async def create_unit_of_measure(
    body: CrearUnidadMedidaRequest,
    request: Request,
    _user=Depends(require_roles("planeacion", "admin_sistema")),
):
    item = await CreateUnitOfMeasure(request.app.state.unit_of_measure_repository).execute(
        key=body.clave, name=body.nombre, plural=body.plural
    )
    return UnidadMedidaRespuesta.from_domain(item)


@router.patch(
    "/unidades-medida/{item_id}",
    response_model=UnidadMedidaRespuesta,
    summary="Editar unidad de medida",
)
async def update_unit_of_measure(
    item_id: int,
    body: CrearUnidadMedidaRequest,
    request: Request,
    _user=Depends(require_roles("planeacion", "admin_sistema")),
):
    item = await UpdateUnitOfMeasure(request.app.state.unit_of_measure_repository).execute(
        item_id,
        key=body.clave,
        name=body.nombre,
        plural=body.plural,
        expected_version=body.version,
    )
    return UnidadMedidaRespuesta.from_domain(item)


@router.post(
    "/unidades-medida/{item_id}/desactivar",
    response_model=UnidadMedidaRespuesta,
    summary="Desactivar unidad de medida",
)
async def deactivate_unit_of_measure(
    item_id: int,
    request: Request,
    version: int | None = Query(default=None, ge=1),
    _user=Depends(require_roles("planeacion", "admin_sistema")),
):
    item = await DeactivateUnitOfMeasure(request.app.state.unit_of_measure_repository).execute(
        item_id, version
    )
    return UnidadMedidaRespuesta.from_domain(item)
