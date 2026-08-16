"""Endpoints de autenticacion y administracion de usuarios."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status

from app.core.schemas import ErrorResponse
from app.core.security import get_access_claims, get_current_user, require_roles

from ..application.dto import (
    ChangeUserStatusCommand,
    LogoutCommand,
    RefreshCommand,
    RegisterUserCommand,
    UpdateUserCommand,
)
from ..application.use_cases.authenticate_user import AuthenticateUser
from ..application.use_cases.change_user_status import DeactivateUser, ReactivateUser
from ..application.use_cases.logout_user import LogoutUser
from ..application.use_cases.password_setup import InviteUser, SetInitialPassword
from ..application.use_cases.refresh_session import RefreshSession
from ..application.use_cases.update_user import UpdateUser
from ..domain.value_objects import Role
from .dependencies import (
    get_authenticate_user_use_case,
    get_deactivate_user_use_case,
    get_invite_user_use_case,
    get_logout_user_use_case,
    get_reactivate_user_use_case,
    get_refresh_session_use_case,
    get_set_initial_password_use_case,
    get_update_user_use_case,
)
from .schemas import (
    ActualizarUsuarioRequest,
    ConfigurarContrasenaRequest,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    RefreshRequest,
    UsuarioCreateRequest,
    UsuarioResponse,
    ValidarEnlaceContrasenaRequest,
)

TAG = "Usuarios y roles"

router = APIRouter()


@router.post(
    "/auth/login",
    response_model=LoginResponse,
    summary="Autenticar usuario institucional",
    description="Recibe correo y contrasena, devuelve access/refresh tokens.",
    responses={401: {"model": ErrorResponse, "description": "Credenciales invalidas."}},
    tags=[TAG],
)
async def login(
    body: LoginRequest,
    use_case: AuthenticateUser = Depends(get_authenticate_user_use_case),
) -> LoginResponse:
    result = await use_case.execute(email=str(body.correo), password=body.contrasena)
    return LoginResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        token_type="bearer",
        expires_in=result.expires_in,
    )


@router.post(
    "/auth/refresh",
    response_model=LoginResponse,
    summary="Rotar refresh token",
    description="Invalida el refresh token recibido y emite un par nuevo.",
    responses={
        401: {"model": ErrorResponse, "description": "Refresh token invalido o reutilizado."}
    },
    tags=[TAG],
)
async def refresh(
    body: RefreshRequest,
    use_case: RefreshSession = Depends(get_refresh_session_use_case),
) -> LoginResponse:
    result = await use_case.execute(RefreshCommand(refresh_token=body.refresh_token))
    return LoginResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        token_type="bearer",
        expires_in=result.expires_in,
    )


@router.post(
    "/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cerrar sesion y revocar tokens",
    description="Revoca el access token actual y el refresh token de la sesion.",
    responses={401: {"model": ErrorResponse, "description": "Token invalido."}},
    tags=[TAG],
)
async def logout(
    body: LogoutRequest,
    claims=Depends(get_access_claims),
    use_case: LogoutUser = Depends(get_logout_user_use_case),
) -> Response:
    await use_case.execute(
        LogoutCommand(
            access_subject=claims.subject,
            access_token_id=claims.token_id,
            access_expires_at=claims.expires_at,
            refresh_token=body.refresh_token,
        )
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/auth/me",
    response_model=UsuarioResponse,
    summary="Consultar usuario autenticado",
    responses={401: {"model": ErrorResponse, "description": "Token invalido."}},
    tags=[TAG],
)
async def current_user(user=Depends(get_current_user)) -> UsuarioResponse:
    return UsuarioResponse.from_domain(user)


@router.post(
    "/usuarios",
    response_model=UsuarioResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar usuario y asignar roles",
    description="Solo Planeacion o Administracion del sistema puede crear usuarios.",
    responses={
        403: {"model": ErrorResponse, "description": "Rol insuficiente."},
        409: {"model": ErrorResponse, "description": "El correo ya esta registrado."},
    },
    tags=[TAG],
)
async def create_user(
    body: UsuarioCreateRequest,
    current_user=Depends(require_roles(Role.PLANEACION.value, Role.ADMIN_SISTEMA.value)),
    use_case: InviteUser = Depends(get_invite_user_use_case),
) -> UsuarioResponse:
    user = await use_case.execute(
        RegisterUserCommand(
            email=str(body.correo),
            full_name=body.nombre,
            password=body.contrasena or "",
            roles=body.roles,
            area_id=body.area_id,
            actor_id=current_user.id,
        )
    )
    return UsuarioResponse.from_domain(user)


@router.post(
    "/auth/password-setup/validar",
    summary="Validar enlace de configuracion de contrasena",
    tags=[TAG],
)
async def validate_password_setup_link(
    body: ValidarEnlaceContrasenaRequest,
    use_case: SetInitialPassword = Depends(get_set_initial_password_use_case),
):
    return {"valido": await use_case.validate_token(body.token)}


@router.post(
    "/auth/password-setup",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Configurar contrasena mediante invitacion",
    tags=[TAG],
)
async def set_initial_password(
    body: ConfigurarContrasenaRequest,
    use_case: SetInitialPassword = Depends(get_set_initial_password_use_case),
) -> Response:
    await use_case.execute(body.token, body.contrasena)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/usuarios",
    response_model=list[UsuarioResponse],
    summary="Consultar usuarios institucionales",
    responses={403: {"model": ErrorResponse, "description": "Rol insuficiente."}},
    tags=[TAG],
)
async def list_users(
    request: Request,
    _current_user=Depends(require_roles(Role.PLANEACION.value, Role.ADMIN_SISTEMA.value)),
) -> list[UsuarioResponse]:
    users = await request.app.state.user_repository.list()
    return [UsuarioResponse.from_domain(user) for user in users]


@router.patch(
    "/usuarios/{user_id}",
    response_model=UsuarioResponse,
    summary="Editar usuario institucional",
    responses={
        403: {"model": ErrorResponse, "description": "Rol insuficiente."},
        404: {"model": ErrorResponse, "description": "Usuario inexistente."},
        409: {"model": ErrorResponse, "description": "El correo ya esta registrado."},
    },
    tags=[TAG],
)
async def update_user(
    user_id: int,
    body: ActualizarUsuarioRequest,
    current_user=Depends(require_roles(Role.PLANEACION.value, Role.ADMIN_SISTEMA.value)),
    use_case: UpdateUser = Depends(get_update_user_use_case),
) -> UsuarioResponse:
    user = await use_case.execute(
        UpdateUserCommand(
            user_id=user_id,
            email=str(body.correo) if body.correo else None,
            full_name=body.nombre,
            roles=body.roles,
            area_id=body.area_id,
            actor_id=current_user.id,
        )
    )
    return UsuarioResponse.from_domain(user)


@router.post(
    "/usuarios/{user_id}/desactivar",
    response_model=UsuarioResponse,
    summary="Desactivar usuario y revocar sus sesiones",
    responses={
        403: {"model": ErrorResponse, "description": "Rol insuficiente."},
        404: {"model": ErrorResponse, "description": "Usuario inexistente."},
        422: {"model": ErrorResponse, "description": "El usuario ya esta desactivado."},
    },
    tags=[TAG],
)
async def deactivate_user(
    user_id: int,
    current_user=Depends(require_roles(Role.PLANEACION.value, Role.ADMIN_SISTEMA.value)),
    use_case: DeactivateUser = Depends(get_deactivate_user_use_case),
) -> UsuarioResponse:
    user = await use_case.execute(
        ChangeUserStatusCommand(user_id=user_id, actor_id=current_user.id)
    )
    return UsuarioResponse.from_domain(user)


@router.post(
    "/usuarios/{user_id}/reactivar",
    response_model=UsuarioResponse,
    summary="Reactivar usuario institucional",
    responses={
        403: {"model": ErrorResponse, "description": "Solo el administrador puede reactivar."},
        404: {"model": ErrorResponse, "description": "Usuario inexistente."},
        422: {"model": ErrorResponse, "description": "El usuario ya esta activo."},
    },
    tags=[TAG],
)
async def reactivate_user(
    user_id: int,
    current_user=Depends(require_roles(Role.ADMIN_SISTEMA.value)),
    use_case: ReactivateUser = Depends(get_reactivate_user_use_case),
) -> UsuarioResponse:
    user = await use_case.execute(
        ChangeUserStatusCommand(user_id=user_id, actor_id=current_user.id)
    )
    return UsuarioResponse.from_domain(user)
