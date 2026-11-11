from fastapi import APIRouter, Depends, Request

from app.core.error_responses import los_errores_que_devuelve
from app.core.security import require_roles
from app.shared.domain.exceptions import AuthenticationError, ForbiddenError

from .schemas import (
    AvisoDePlaneacionRequest,
    AvisoEntregadoRespuesta,
    AvisoRedactadoRespuesta,
)

router = APIRouter(prefix="/avisos", tags=["Avisos"])

ROLES_QUE_REDACTAN_AVISOS = ("planeacion", "planeacion_admin", "admin_sistema")

requiere_redactar = require_roles(*ROLES_QUE_REDACTAN_AVISOS)

SIN_SESION_NI_PERMISO = los_errores_que_devuelve(AuthenticationError, ForbiddenError)


@router.post(
    "",
    response_model=AvisoEntregadoRespuesta,
    summary="Redactar un aviso dirigido a las areas",
    responses=SIN_SESION_NI_PERMISO,
)
async def redactar_un_aviso(
    body: AvisoDePlaneacionRequest,
    request: Request,
    usuario=Depends(requiere_redactar),
) -> AvisoEntregadoRespuesta:
    redactado = await request.app.state.area_notices.planeacion_redacto(
        body.areas,
        titulo=body.titulo,
        mensaje=body.mensaje,
        creado_por=usuario.id,
        destino_ruta=body.destino_ruta,
        vigente_hasta=body.vigente_hasta,
        adjuntos=body.los_adjuntos(),
    )
    return AvisoEntregadoRespuesta.from_domain(redactado)


@router.get(
    "",
    response_model=list[AvisoRedactadoRespuesta],
    summary="Consultar los avisos redactados y cuantas areas los leyeron",
    responses=SIN_SESION_NI_PERMISO,
)
async def consultar_los_avisos(
    request: Request,
    _usuario=Depends(requiere_redactar),
) -> list[AvisoRedactadoRespuesta]:
    cifras = await request.app.state.las_cifras_de_lectura.de_los_avisos()
    return [AvisoRedactadoRespuesta.from_domain(una) for una in cifras]
