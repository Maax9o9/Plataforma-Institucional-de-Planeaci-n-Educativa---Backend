"""Endpoints de areas e instrumentos institucionales."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, status

from app.core.schemas import ErrorResponse
from app.core.security import get_current_user, require_roles

from ..application.dto import (
    ChangeCatalogStatusCommand,
    CreateAreaCommand,
    CreateInstrumentCommand,
    UpdateAreaCommand,
    UpdateInstrumentCommand,
)
from ..application.use_cases.create_area import CreateArea
from ..application.use_cases.create_instrument import CreateInstrument
from ..application.use_cases.update_area import DeactivateArea, UpdateArea
from ..application.use_cases.update_instrument import DeactivateInstrument, UpdateInstrument
from .dependencies import (
    get_create_area_use_case,
    get_create_instrument_use_case,
    get_deactivate_area_use_case,
    get_deactivate_instrument_use_case,
    get_update_area_use_case,
    get_update_instrument_use_case,
)
from .schemas import (
    ActualizarAreaRequest,
    ActualizarInstrumentoRequest,
    AreaRespuesta,
    CrearAreaRequest,
    CrearInstrumentoRequest,
    InstrumentoRespuesta,
)

TAG = "Catalogos institucionales"
router = APIRouter(prefix="/catalogos", tags=[TAG])


@router.get(
    "/areas",
    response_model=list[AreaRespuesta],
    summary="Consultar areas institucionales",
    responses={401: {"model": ErrorResponse, "description": "Autenticacion requerida."}},
)
async def list_areas(
    request: Request,
    activo: bool | None = Query(default=True),
    user=Depends(get_current_user),
) -> list[AreaRespuesta]:
    del user
    areas = await request.app.state.area_repository.list(active_only=False)
    if activo is not None:
        areas = [area for area in areas if area.is_active is activo]
    return [AreaRespuesta.from_domain(area) for area in areas]


@router.post(
    "/areas",
    response_model=AreaRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar area institucional",
    responses={
        403: {"model": ErrorResponse, "description": "Rol insuficiente."},
        409: {"model": ErrorResponse, "description": "Codigo duplicado."},
    },
)
async def create_area(
    body: CrearAreaRequest,
    current_user=Depends(require_roles("planeacion", "admin_sistema")),
    use_case: CreateArea = Depends(get_create_area_use_case),
) -> AreaRespuesta:
    area = await use_case.execute(
        CreateAreaCommand(
            code=body.codigo,
            name=body.nombre,
            parent_id=body.area_padre_id,
            area_type=body.tipo,
            color=body.color,
            actor_id=current_user.id,
        )
    )
    return AreaRespuesta.from_domain(area)


@router.patch(
    "/areas/{area_id}",
    response_model=AreaRespuesta,
    summary="Editar area institucional",
    responses={
        403: {"model": ErrorResponse, "description": "Rol insuficiente."},
        404: {"model": ErrorResponse, "description": "Area inexistente."},
    },
)
async def update_area(
    area_id: int,
    body: ActualizarAreaRequest,
    current_user=Depends(require_roles("planeacion", "admin_sistema")),
    use_case: UpdateArea = Depends(get_update_area_use_case),
) -> AreaRespuesta:
    area = await use_case.execute(
        UpdateAreaCommand(
            area_id=area_id,
            code=body.codigo,
            name=body.nombre,
            parent_id=body.area_padre_id,
            area_type=body.tipo,
            color=body.color,
            actor_id=current_user.id,
            expected_version=body.version,
        )
    )
    return AreaRespuesta.from_domain(area)


@router.post(
    "/areas/{area_id}/desactivar",
    response_model=AreaRespuesta,
    summary="Desactivar area institucional",
    responses={
        403: {"model": ErrorResponse, "description": "Rol insuficiente."},
        404: {"model": ErrorResponse, "description": "Area inexistente."},
    },
)
async def deactivate_area(
    area_id: int,
    version: int | None = Query(default=None, ge=1),
    current_user=Depends(require_roles("planeacion", "admin_sistema")),
    use_case: DeactivateArea = Depends(get_deactivate_area_use_case),
) -> AreaRespuesta:
    area = await use_case.execute(
        ChangeCatalogStatusCommand(
            item_id=area_id,
            actor_id=current_user.id,
            expected_version=version,
        )
    )
    return AreaRespuesta.from_domain(area)


@router.get(
    "/instrumentos",
    response_model=list[InstrumentoRespuesta],
    summary="Consultar instrumentos institucionales",
    responses={401: {"model": ErrorResponse, "description": "Autenticacion requerida."}},
)
async def list_instruments(
    request: Request,
    activo: bool | None = Query(default=True),
    user=Depends(get_current_user),
) -> list[InstrumentoRespuesta]:
    del user
    instruments = await request.app.state.instrument_repository.list(active_only=False)
    if activo is not None:
        instruments = [item for item in instruments if item.is_active is activo]
    return [InstrumentoRespuesta.from_domain(instrument) for instrument in instruments]


@router.post(
    "/instrumentos",
    response_model=InstrumentoRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar instrumento institucional",
    responses={
        403: {"model": ErrorResponse, "description": "Rol insuficiente."},
        409: {"model": ErrorResponse, "description": "Codigo duplicado."},
    },
)
async def create_instrument(
    body: CrearInstrumentoRequest,
    current_user=Depends(require_roles("planeacion", "admin_sistema")),
    use_case: CreateInstrument = Depends(get_create_instrument_use_case),
) -> InstrumentoRespuesta:
    instrument = await use_case.execute(
        CreateInstrumentCommand(
            code=body.codigo,
            name=body.nombre,
            description=body.descripcion,
            actor_id=current_user.id,
        )
    )
    return InstrumentoRespuesta.from_domain(instrument)


@router.patch(
    "/instrumentos/{instrument_id}",
    response_model=InstrumentoRespuesta,
    summary="Editar instrumento institucional",
    responses={
        403: {"model": ErrorResponse, "description": "Rol insuficiente."},
        404: {"model": ErrorResponse, "description": "Instrumento inexistente."},
    },
)
async def update_instrument(
    instrument_id: int,
    body: ActualizarInstrumentoRequest,
    current_user=Depends(require_roles("planeacion", "admin_sistema")),
    use_case: UpdateInstrument = Depends(get_update_instrument_use_case),
) -> InstrumentoRespuesta:
    instrument = await use_case.execute(
        UpdateInstrumentCommand(
            instrument_id=instrument_id,
            code=body.codigo,
            name=body.nombre,
            description=body.descripcion,
            actor_id=current_user.id,
            expected_version=body.version,
        )
    )
    return InstrumentoRespuesta.from_domain(instrument)


@router.post(
    "/instrumentos/{instrument_id}/desactivar",
    response_model=InstrumentoRespuesta,
    summary="Desactivar instrumento institucional",
    responses={
        403: {"model": ErrorResponse, "description": "Rol insuficiente."},
        404: {"model": ErrorResponse, "description": "Instrumento inexistente."},
    },
)
async def deactivate_instrument(
    instrument_id: int,
    version: int | None = Query(default=None, ge=1),
    current_user=Depends(require_roles("planeacion", "admin_sistema")),
    use_case: DeactivateInstrument = Depends(get_deactivate_instrument_use_case),
) -> InstrumentoRespuesta:
    instrument = await use_case.execute(
        ChangeCatalogStatusCommand(
            item_id=instrument_id,
            actor_id=current_user.id,
            expected_version=version,
        )
    )
    return InstrumentoRespuesta.from_domain(instrument)
