from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, status

from app.core.authorization import (
    ROLES_QUE_LEEN_EL_POA_DE_CUALQUIER_AREA,
    ensure_area_or_institutional_reader,
    ensure_area_or_planning,
)
from app.core.error_responses import los_errores_que_devuelve
from app.core.security import require_roles
from app.modules.institutional_catalogs.domain.strategic_tree_entities import (
    MAYOR_ENTERO_DE_LA_BASE,
)
from app.shared.domain.calendar import institutional_today
from app.shared.domain.exceptions import (
    AuthenticationError,
    ForbiddenError,
    ResourceNotFoundError,
)

from ..application.use_cases.manage_poa_area import (
    OpenInstitutionalPoa,
    OpenInstitutionalPoaCommand,
    ReopenPoaArea,
    ReopenPoaAreaCommand,
    SaveActivityCommand,
    SavePoaActivity,
    SubmitPoaArea,
    SubmitPoaAreaCommand,
)
from ..domain.entities import (
    Activity,
    PoaArea,
    el_registro_no_esta_habilitado,
    reasons_it_cannot_be_submitted,
)
from .dependencies import (
    get_open_institutional_poa,
    get_reopen_poa_area,
    get_save_poa_activity,
    get_submit_poa_area,
)
from .schemas import (
    AbrirElPoaRequest,
    ActividadRespuesta,
    ActualizarActividadRequest,
    AperturaDelPoaRespuesta,
    CrearActividadRequest,
    PoaDelAreaRespuesta,
    PresentarPoaDelAreaRequest,
    ReabrirElPoaRequest,
)

router = APIRouter(prefix="/poa-institucional", tags=["POA del área"])

ROLES_QUE_FORMULAN = ("planeacion", "planeacion_admin", "admin_sistema", "capturista_poa")
ROLES_QUE_CONSULTAN = (*ROLES_QUE_FORMULAN, "responsable_area", "rectoria", "revisor_poa")
ROLES_QUE_ABREN = ("planeacion", "planeacion_admin", "admin_sistema")

requiere_formular = require_roles(*ROLES_QUE_FORMULAN)
requiere_consultar = require_roles(*ROLES_QUE_CONSULTAN)
requiere_abrir = require_roles(*ROLES_QUE_ABREN)

SIN_SESION_NI_PERMISO = los_errores_que_devuelve(AuthenticationError, ForbiddenError)
SIN_SESION_NI_PERMISO_NI_POA_ABIERTO = los_errores_que_devuelve(
    AuthenticationError, ForbiddenError, ResourceNotFoundError
)

IdEnLaRuta = Annotated[int, Path(ge=1, le=MAYOR_ENTERO_DE_LA_BASE)]
EjercicioEnLaConsulta = Annotated[int, Query(ge=1, le=MAYOR_ENTERO_DE_LA_BASE)]

EL_REGISTRO_SIN_HABILITAR = el_registro_no_esta_habilitado(None)


async def _respuesta(
    request: Request, poa_area: PoaArea, *, incluir_inactivas: bool = False
) -> PoaDelAreaRespuesta:
    repositorio = request.app.state.poa_area_repository
    todas: list[Activity] = await repositorio.list_activities(poa_area.id, include_inactive=True)
    falta = reasons_it_cannot_be_submitted(
        todas,
        area_has_person_in_charge=await request.app.state.area_leadership.has_person_in_charge(
            poa_area.area_id
        ),
    )
    return PoaDelAreaRespuesta.from_domain(
        poa_area,
        todas if incluir_inactivas else [una for una in todas if una.is_active],
        falta_para_presentar=falta,
        ventana=await repositorio.current_capture_window(poa_area.id),
        hoy=institutional_today(),
    )


async def _el_poa_del_area_ya_abierto(request: Request, ejercicio_id: int, area_id: int) -> PoaArea:
    poa_area = await request.app.state.poa_area_repository.find_poa_area(ejercicio_id, area_id)
    if poa_area is None:
        raise ResourceNotFoundError(EL_REGISTRO_SIN_HABILITAR)
    return poa_area


@router.get(
    "/areas/{area_id}",
    response_model=PoaDelAreaRespuesta,
    summary="Consultar el POA del area en un ejercicio",
    responses=SIN_SESION_NI_PERMISO_NI_POA_ABIERTO,
)
async def consultar_el_poa_del_area(
    area_id: IdEnLaRuta,
    request: Request,
    ejercicio_id: EjercicioEnLaConsulta,
    incluir_inactivas: bool = Query(default=False),
    usuario=Depends(requiere_consultar),
) -> PoaDelAreaRespuesta:
    ensure_area_or_institutional_reader(
        usuario, area_id, lectores=ROLES_QUE_LEEN_EL_POA_DE_CUALQUIER_AREA
    )
    poa_area = await _el_poa_del_area_ya_abierto(request, ejercicio_id, area_id)
    return await _respuesta(request, poa_area, incluir_inactivas=incluir_inactivas)


@router.post(
    "/abrir",
    response_model=AperturaDelPoaRespuesta,
    summary="Abrir el POA institucional de un ejercicio para las areas",
    responses=SIN_SESION_NI_PERMISO,
)
async def abrir_el_poa_institucional(
    body: AbrirElPoaRequest,
    ejercicio_id: EjercicioEnLaConsulta,
    usuario=Depends(requiere_abrir),
    abrir: OpenInstitutionalPoa = Depends(get_open_institutional_poa),
) -> AperturaDelPoaRespuesta:
    reparto = await abrir.execute(
        OpenInstitutionalPoaCommand(
            exercise_id=ejercicio_id,
            area_ids=body.areas,
            opens_on=body.desde,
            closes_on=body.hasta,
            opened_by=usuario.id,
        )
    )
    return AperturaDelPoaRespuesta.from_domain(ejercicio_id, reparto)


@router.post(
    "/areas/{area_id}/reabrir",
    response_model=PoaDelAreaRespuesta,
    summary="Reabrir el POA del area del ejercicio con un periodo de captura nuevo",
    responses=SIN_SESION_NI_PERMISO_NI_POA_ABIERTO,
)
async def reabrir_el_poa_del_area(
    area_id: IdEnLaRuta,
    body: ReabrirElPoaRequest,
    request: Request,
    ejercicio_id: EjercicioEnLaConsulta,
    usuario=Depends(requiere_abrir),
    reabrir: ReopenPoaArea = Depends(get_reopen_poa_area),
) -> PoaDelAreaRespuesta:
    reabierto = await reabrir.execute(
        ReopenPoaAreaCommand(
            exercise_id=ejercicio_id,
            area_id=area_id,
            opens_on=body.desde,
            closes_on=body.hasta,
            reason=body.motivo,
            opened_by=usuario.id,
        )
    )
    return await _respuesta(request, reabierto.poa_area)


@router.post(
    "/areas/{area_id}/actividades",
    response_model=ActividadRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar una actividad en el POA del area",
    responses=SIN_SESION_NI_PERMISO_NI_POA_ABIERTO,
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
    responses=SIN_SESION_NI_PERMISO_NI_POA_ABIERTO,
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
    responses=SIN_SESION_NI_PERMISO_NI_POA_ABIERTO,
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
