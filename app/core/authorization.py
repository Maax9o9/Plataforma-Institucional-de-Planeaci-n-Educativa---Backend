"""Politicas transversales de autorizacion por recurso."""

from __future__ import annotations

from app.shared.application.actor import ActorContext
from app.shared.domain.exceptions import ForbiddenError


def actor_from_user(user) -> ActorContext:
    return ActorContext.from_user(user)


ROLES_QUE_VEN_TODA_AREA = frozenset({"planeacion", "planeacion_admin", "admin_sistema", "rectoria"})


def ensure_owner_or_planning(user, owner_id: int) -> None:
    actor = actor_from_user(user)
    if actor.is_planning or actor.id == owner_id:
        return
    raise ForbiddenError()


def ensure_area_or_planning(user, area_id: int | None) -> None:
    actor = actor_from_user(user)
    if actor.is_planning or (actor.area_id is not None and actor.area_id == area_id):
        return
    raise ForbiddenError("El recurso no pertenece al area del usuario.")


def ensure_area_or_institutional_reader(user, area_id: int | None, *, lectores: set[str]) -> None:
    if actor_from_user(user).has_any_role(*lectores):
        return
    ensure_area_or_planning(user, area_id)
