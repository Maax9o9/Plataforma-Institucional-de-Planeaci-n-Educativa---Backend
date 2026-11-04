from fastapi import APIRouter, Depends, Request

from app.core.error_responses import los_errores_que_devuelve
from app.core.security import require_roles
from app.shared.domain.exceptions import AuthenticationError, ForbiddenError

from .schemas import AvisoDePlaneacionRequest, AvisoEntregadoRespuesta

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
    _usuario=Depends(requiere_redactar),
) -> AvisoEntregadoRespuesta:
    entregados = await request.app.state.area_notices.planeacion_redacto(
        body.areas, titulo=body.titulo, mensaje=body.mensaje
    )
    return AvisoEntregadoRespuesta.from_domain(entregados)
