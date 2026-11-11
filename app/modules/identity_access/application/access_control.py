"""Impide la escalada de privilegios al administrar cuentas."""

from app.shared.domain.exceptions import ForbiddenError

from ..domain.entities import User
from ..domain.ports.user_repository import UserRepository
from ..domain.value_objects import Role

ADMIN_ROLES = {Role.ADMIN_SISTEMA, Role.PLANEACION_ADMIN}

ROLES_QUE_UN_AREA_ASIGNA = {Role.CAPTURISTA_POA, Role.CONSULTA}


async def ensure_can_manage_user(
    repository: UserRepository,
    actor_id: int | None,
    *,
    assigned_roles: set[Role] | frozenset[Role] = frozenset(),
    target: User | None = None,
    area_id: int | None = None,
) -> None:
    actor = await repository.get_by_id(actor_id) if actor_id is not None else None
    if actor is None or not actor.is_active:
        raise ForbiddenError("Se requiere un usuario activo para administrar cuentas.")
    if actor.has_any_role({role.value for role in ADMIN_ROLES}):
        return
    if not actor.has_any_role({Role.PLANEACION.value}):
        if actor.has_any_role({Role.RESPONSABLE_AREA.value}):
            ensure_area_lead_stays_in_their_area(
                actor, assigned_roles=assigned_roles, target=target, area_id=area_id
            )
            return
        raise ForbiddenError("Sólo Planeación puede administrar cuentas.")
    if ADMIN_ROLES.intersection(assigned_roles) or (
        target is not None and ADMIN_ROLES.intersection(target.roles)
    ):
        raise ForbiddenError(
            "Sólo un administrador puede otorgar o modificar acceso administrativo."
        )


def ensure_area_lead_stays_in_their_area(
    actor: User,
    *,
    assigned_roles: set[Role] | frozenset[Role],
    target: User | None,
    area_id: int | None,
) -> None:
    if actor.area_id is None:
        raise ForbiddenError(
            "La función de responsable de área se ejerce desde un área, y esta cuenta no "
            "tiene ninguna asignada."
        )
    fuera_de_su_alcance = {
        Role.from_value(role) if isinstance(role, str) else role for role in assigned_roles
    } - ROLES_QUE_UN_AREA_ASIGNA
    if fuera_de_su_alcance:
        raise ForbiddenError(
            "El responsable de área sólo da de alta a quien captura o consulta el programa "
            "de su área. Las demás funciones las asigna la Dirección de Planeación."
        )
    if area_id is not None and area_id != actor.area_id:
        raise ForbiddenError("El responsable de área sólo administra a la gente de su área.")
    if target is not None and target.area_id != actor.area_id:
        raise ForbiddenError("El responsable de área sólo administra a la gente de su área.")
