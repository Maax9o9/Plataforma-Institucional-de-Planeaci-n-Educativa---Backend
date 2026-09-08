"""Endpoints de autenticacion y administracion de usuarios."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.core.schemas import ErrorResponse
from app.core.security import get_current_user, get_logout_claims, require_roles
from app.shared.domain.exceptions import AuthenticationError, RateLimitError

from ..application.dto import (
    ChangeUserStatusCommand,
    LogoutCommand,
    RefreshCommand,
    RegisterUserCommand,
    UpdateUserCommand,
)
from ..application.use_cases.authenticate_user import AuthenticateUser
from ..application.use_cases.change_password import ChangeAdminPassword
from ..application.use_cases.change_user_status import DeactivateUser, ReactivateUser
from ..application.use_cases.logout_user import LogoutUser
from ..application.use_cases.password_setup import InviteUser, SetInitialPassword
from ..application.use_cases.refresh_session import RefreshSession
from ..application.use_cases.update_user import UpdateUser
from ..domain.value_objects import Role
from .cookies import clear_refresh_cookie, read_refresh_cookie, set_refresh_cookie
from .dependencies import (
    get_authenticate_user_use_case,
    get_change_admin_password_use_case,
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
    CambiarContrasenaAdminRequest,
    ConfigurarContrasenaRequest,
    LoginRequest,
    LoginResponse,
    PaginaUsuariosResponse,
    UsuarioCreateRequest,
    UsuarioResponse,
    ValidarEnlaceContrasenaRequest,
)

TAG = "Usuarios y roles"

router = APIRouter()


@router.post(
    "/auth/cambiar-contrasena",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cambiar la contraseña de mi cuenta administrativa",
    tags=[TAG],
)
async def change_admin_password(
    body: CambiarContrasenaAdminRequest,
    request: Request,
    response: Response,
    current_user=Depends(require_roles("admin_sistema", "planeacion_admin")),
    use_case: ChangeAdminPassword = Depends(get_change_admin_password_use_case),
) -> None:
    key = f"password-change:{current_user.id}"
    limiter = request.app.state.login_rate_limiter
    retry_after = await limiter.retry_after(key)
    if retry_after:
        raise RateLimitError(details={"retry_after": retry_after})
    try:
        await use_case.execute(
            current_user.id,
            body.contrasena_actual.get_secret_value(),
            body.contrasena_nueva.get_secret_value(),
        )
    except AuthenticationError:
        await limiter.record_failure(key)
        raise
    await limiter.clear(key)
    clear_refresh_cookie(response, request.app.state.settings)


@router.post(
    "/auth/login",
    response_model=LoginResponse,
    summary="Autenticar usuario institucional",
    description="Devuelve el access token y guarda el refresh token en cookie HttpOnly.",
    responses={
        401: {"model": ErrorResponse, "description": "Credenciales invalidas."},
        429: {"model": ErrorResponse, "description": "Demasiados intentos fallidos."},
    },
    tags=[TAG],
)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    use_case: AuthenticateUser = Depends(get_authenticate_user_use_case),
) -> LoginResponse:
    client_host = request.client.host if request.client else "unknown"
    rate_limit_key = f"{client_host}:{str(body.correo).casefold()}"
    retry_after = await request.app.state.login_rate_limiter.retry_after(rate_limit_key)
    if retry_after:
        raise RateLimitError(details={"retry_after": retry_after})
    try:
        result = await use_case.execute(email=str(body.correo), password=body.contrasena)
    except AuthenticationError:
        await request.app.state.login_rate_limiter.record_failure(rate_limit_key)
        raise
    await request.app.state.login_rate_limiter.clear(rate_limit_key)
    set_refresh_cookie(response, result.refresh_token, request.app.state.settings)
    return LoginResponse(
        access_token=result.access_token,
        token_type="bearer",
        expires_in=result.expires_in,
    )


@router.post(
    "/auth/refresh",
    response_model=LoginResponse,
    summary="Rotar refresh token",
    description="Rota la cookie HttpOnly de sesion y devuelve un access token nuevo.",
    responses={
        401: {"model": ErrorResponse, "description": "Refresh token invalido o reutilizado."}
    },
    tags=[TAG],
)
async def refresh(
    request: Request,
    response: Response,
    use_case: RefreshSession = Depends(get_refresh_session_use_case),
) -> LoginResponse:
    settings = request.app.state.settings
    refresh_token = read_refresh_cookie(request, settings)
    assert refresh_token is not None
    result = await use_case.execute(RefreshCommand(refresh_token=refresh_token))
    set_refresh_cookie(response, result.refresh_token, settings)
    return LoginResponse(
        access_token=result.access_token,
        token_type="bearer",
        expires_in=result.expires_in,
    )


@router.post(
    "/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cerrar sesion y revocar tokens",
    description=(
        "Revoca el access token actual y, cuando la cookie esta presente, toda su "
        "familia de refresh tokens. La cookie es opcional para permitir logout repetido."
    ),
    responses={401: {"model": ErrorResponse, "description": "Token invalido."}},
    tags=[TAG],
)
async def logout(
    request: Request,
    response: Response,
    claims=Depends(get_logout_claims),
    use_case: LogoutUser = Depends(get_logout_user_use_case),
) -> Response:
    settings = request.app.state.settings
    refresh_token = read_refresh_cookie(request, settings, required=False)
    await use_case.execute(
        LogoutCommand(
            access_subject=claims.subject,
            access_token_id=claims.token_id,
            access_expires_at=claims.expires_at,
            refresh_token=refresh_token,
        )
    )
    clear_refresh_cookie(response, settings)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


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
    response_model=PaginaUsuariosResponse,
    summary="Consultar usuarios institucionales",
    responses={403: {"model": ErrorResponse, "description": "Rol insuficiente."}},
    tags=[TAG],
)
async def list_users(
    request: Request,
    q: str | None = Query(default=None),
    activo: bool | None = Query(default=None),
    rol: Role | None = Query(default=None),
    area_id: int | None = Query(default=None),
    sort: Literal["nombre", "correo", "id"] = Query(default="nombre"),
    order: Literal["asc", "desc"] = Query(default="asc"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    _current_user=Depends(require_roles(Role.PLANEACION.value, Role.ADMIN_SISTEMA.value)),
) -> PaginaUsuariosResponse:
    users = await request.app.state.user_repository.list()
    if q:
        normalized = q.strip().casefold()
        users = [
            user
            for user in users
            if normalized in user.full_name.casefold() or normalized in user.email.value.casefold()
        ]
    if activo is not None:
        users = [user for user in users if user.is_active is activo]
    if rol is not None:
        users = [user for user in users if rol in user.roles]
    if area_id is not None:
        users = [user for user in users if user.area_id == area_id]
    key = {
        "nombre": lambda user: user.full_name.casefold(),
        "correo": lambda user: user.email.value,
        "id": lambda user: user.id,
    }[sort]
    users = sorted(users, key=key, reverse=order == "desc")
    total = len(users)
    return PaginaUsuariosResponse(
        items=[UsuarioResponse.from_domain(user) for user in users[offset : offset + limit]],
        total=total,
        offset=offset,
        limit=limit,
    )


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
            notify_email=body.notificar_correo,
            expected_version=body.version,
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
