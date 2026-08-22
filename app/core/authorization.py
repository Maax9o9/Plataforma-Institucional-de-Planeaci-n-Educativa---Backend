"""Politicas transversales de autorizacion por recurso."""

from __future__ import annotations

from app.shared.application.actor import ActorContext
from app.shared.domain.exceptions import ForbiddenError


def actor_from_user(user) -> ActorContext:
    return ActorContext.from_user(user)


def ensure_owner_or_planning(user, owner_id: int, message: str | None = None) -> None:
    actor = actor_from_user(user)
    if actor.is_planning or actor.id == owner_id:
        return
    raise ForbiddenError(message)


def ensure_area_or_planning(user, area_id: int | None) -> None:
    actor = actor_from_user(user)
    if actor.is_planning or (actor.area_id is not None and actor.area_id == area_id):
        return
    raise ForbiddenError("El recurso no pertenece al area del usuario.")
