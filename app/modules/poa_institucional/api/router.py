from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, status

from app.core.authorization import ensure_area_or_planning
from app.core.error_responses import los_errores_que_devuelve
from app.core.security import require_roles
from app.modules.institutional_catalogs.domain.strategic_tree_entities import (
    MAYOR_ENTERO_DE_LA_BASE,
)
from app.shared.domain.exceptions import ConflictError, ResourceNotFoundError

from ..application.use_cases.manage_poa_area import (
    OpenPoaArea,
    OpenPoaAreaCommand,
    SaveActivityCommand,
    SavePoaActivity,
    SubmitPoaArea,
    SubmitPoaAreaCommand,
)
from ..domain.entities import PoaArea
from .dependencies import get_open_poa_area, get_save_poa_activity, get_submit_poa_area
from .schemas import (
    ActividadRespuesta,
    ActualizarActividadRequest,
    CrearActividadRequest,
    PoaDelAreaRespuesta,
    PresentarPoaDelAreaRequest,
)

router = APIRouter(prefix="/poa-institucional", tags=["POA del área"])

ROLES_QUE_FORMULAN = ("planeacion", "planeacion_admin", "admin_sistema", "capturista_poa")
ROLES_QUE_CONSULTAN = (*ROLES_QUE_FORMULAN, "responsable_area")

requiere_formular = require_roles(*ROLES_QUE_FORMULAN)
requiere_consultar = require_roles(*ROLES_QUE_CONSULTAN)

IdEnLaRuta = Annotated[int, Path(ge=1, le=MAYOR_ENTERO_DE_LA_BASE)]
EjercicioEnLaConsulta = Annotated[int, Query(ge=1, le=MAYOR_ENTERO_DE_LA_BASE)]

EL_POA_DEL_AREA_SIN_ABRIR = (
    "El área todavía no tiene su POA en este ejercicio: consúltelo una vez para abrirlo."
)


async def _actividades(request: Request, poa_area: PoaArea, *, incluir_inactivas: bool):
    return await request.app.state.poa_area_repository.list_activities(
        poa_area.id, include_inactive=incluir_inactivas
    )


async def _respuesta(
    request: Request, poa_area: PoaArea, *, incluir_inactivas: bool = False
) -> PoaDelAreaRespuesta:
    return PoaDelAreaRespuesta.from_domain(
        poa_area, await _actividades(request, poa_area, incluir_inactivas=incluir_inactivas)
    )


async def _el_poa_del_area_ya_abierto(request: Request, ejercicio_id: int, area_id: int) -> PoaArea:
    poa_area = await request.app.state.poa_area_repository.find_poa_area(ejercicio_id, area_id)
    if poa_area is None:
        raise ResourceNotFoundError(EL_POA_DEL_AREA_SIN_ABRIR)
    return poa_area


async def _abierto_aunque_otro_lo_abra_a_la_vez(
    abrir: OpenPoaArea, ejercicio_id: int, area_id: int
) -> PoaArea:
    cmd = OpenPoaAreaCommand(exercise_id=ejercicio_id, area_id=area_id)
    try:
        return await abrir.execute(cmd)
    except ConflictError:
        return await abrir.execute(cmd)


@router.get(
    "/areas/{area_id}",
    response_model=PoaDelAreaRespuesta,
    summary="Consultar el POA del area en un ejercicio, abriendolo si hace falta",
)
async def consultar_el_poa_del_area(
    area_id: IdEnLaRuta,
    request: Request,
    ejercicio_id: EjercicioEnLaConsulta,
    incluir_inactivas: bool = Query(default=False),
    usuario=Depends(requiere_consultar),
    abrir: OpenPoaArea = Depends(get_open_poa_area),
) -> PoaDelAreaRespuesta:
    ensure_area_or_planning(usuario, area_id)
    poa_area = await _abierto_aunque_otro_lo_abra_a_la_vez(abrir, ejercicio_id, area_id)
    return await _respuesta(request, poa_area, incluir_inactivas=incluir_inactivas)


@router.post(
    "/areas/{area_id}/actividades",
    response_model=ActividadRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar una actividad en el POA del area",
    responses=los_errores_que_devuelve(ResourceNotFoundError),
)
async def registrar_actividad(
    area_id: IdEnLaRuta,
    body: CrearActividadRequest,
    request: Request,
    ejercicio_id: EjercicioEnLaConsulta,
    usuario=Depends(requiere_formular),
    guardar: SavePoaActivity = Depends(get_save_poa_activity),
) -> ActividadRespuesta:
    ensure_area_or_planning(usuario, area_id)
    poa_area = await _el_poa_del_area_ya_abierto(request, ejercicio_id, area_id)
    actividad = await guardar.execute(
        SaveActivityCommand(poa_area_id=poa_area.id, **body.lo_que_se_mando())
    )
    return ActividadRespuesta.from_domain(actividad)


@router.patch(
    "/areas/{area_id}/actividades/{actividad_id}",
    response_model=ActividadRespuesta,
    summary="Guardar los campos que se manden de una actividad del POA del area",
    responses=los_errores_que_devuelve(ResourceNotFoundError),
)
async def corregir_actividad(
    area_id: IdEnLaRuta,
    actividad_id: IdEnLaRuta,
    body: ActualizarActividadRequest,
    request: Request,
    ejercicio_id: EjercicioEnLaConsulta,
    usuario=Depends(requiere_formular),
    guardar: SavePoaActivity = Depends(get_save_poa_activity),
) -> ActividadRespuesta:
    ensure_area_or_planning(usuario, area_id)
    poa_area = await _el_poa_del_area_ya_abierto(request, ejercicio_id, area_id)
    actividad = await guardar.execute(
        SaveActivityCommand(
            poa_area_id=poa_area.id,
            activity_id=actividad_id,
            version=body.version,
            **body.lo_que_se_mando(),
        )
    )
    return ActividadRespuesta.from_domain(actividad)


@router.post(
    "/areas/{area_id}/presentar",
    response_model=PoaDelAreaRespuesta,
    summary="Presentar el POA del area a Planeacion",
    responses=los_errores_que_devuelve(ResourceNotFoundError),
)
async def presentar_el_poa_del_area(
    area_id: IdEnLaRuta,
    body: PresentarPoaDelAreaRequest,
    request: Request,
    ejercicio_id: EjercicioEnLaConsulta,
    usuario=Depends(requiere_formular),
    enviar: SubmitPoaArea = Depends(get_submit_poa_area),
) -> PoaDelAreaRespuesta:
    ensure_area_or_planning(usuario, area_id)
    poa_area = await _el_poa_del_area_ya_abierto(request, ejercicio_id, area_id)
    enviado = await enviar.execute(
        SubmitPoaAreaCommand(poa_area_id=poa_area.id, version=body.version)
    )
    return await _respuesta(request, enviado)
