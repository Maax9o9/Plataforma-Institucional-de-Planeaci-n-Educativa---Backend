"""Impide la escalada de privilegios al administrar cuentas."""

from app.shared.domain.exceptions import ForbiddenError

from ..domain.entities import User
from ..domain.ports.user_repository import UserRepository
from ..domain.value_objects import Role

ADMIN_ROLES = {Role.ADMIN_SISTEMA, Role.PLANEACION_ADMIN}


async def ensure_can_manage_user(
    repository: UserRepository,
    actor_id: int | None,
    *,
    assigned_roles: set[Role] | frozenset[Role] = frozenset(),
    target: User | None = None,
) -> None:
    actor = await repository.get_by_id(actor_id) if actor_id is not None else None
    if actor is None or not actor.is_active:
        raise ForbiddenError("Se requiere un usuario activo para administrar cuentas.")
    if actor.has_any_role({role.value for role in ADMIN_ROLES}):
        return
    if not actor.has_any_role({Role.PLANEACION.value}):
        raise ForbiddenError("Sólo Planeación puede administrar cuentas.")
    if ADMIN_ROLES.intersection(assigned_roles) or (
        target is not None and ADMIN_ROLES.intersection(target.roles)
    ):
        raise ForbiddenError(
            "Sólo un administrador puede otorgar o modificar acceso administrativo."
        )
