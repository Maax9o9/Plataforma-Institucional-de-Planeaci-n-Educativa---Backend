"""Desactivar/reactivar usuarios y revocar sesiones activas."""

from __future__ import annotations

from app.shared.application.event_bus import EventBus
from app.shared.domain.exceptions import InvalidStateError, ResourceNotFoundError

from ...domain.entities import User
from ...domain.events import UserDeactivated, UserReactivated
from ...domain.ports.refresh_token_repository import RefreshTokenStore
from ...domain.ports.user_repository import UserRepository
from ..access_control import ensure_can_manage_user
from ..dto import ChangeUserStatusCommand


class DeactivateUser:
    def __init__(
        self,
        repository: UserRepository,
        refresh_tokens: RefreshTokenStore,
        event_bus: EventBus,
    ) -> None:
        self.repository = repository
        self.refresh_tokens = refresh_tokens
        self.event_bus = event_bus

    async def execute(self, command: ChangeUserStatusCommand) -> User:
        user = await self.repository.get_by_id(command.user_id)
        if user is None:
            raise ResourceNotFoundError("El usuario no existe.")
        await ensure_can_manage_user(self.repository, command.actor_id, target=user)
        if not user.is_active:
            raise InvalidStateError("El usuario ya esta desactivado.")
        user.deactivate()
        await self.repository.update(user)
        await self.refresh_tokens.revoke_user(user.id)
        await self.event_bus.publish(
            UserDeactivated(
                actor_id=command.actor_id,
                aggregate_type="user",
                aggregate_id=user.id,
                action="deactivated",
                data={"email": user.email.value},
            )
        )
        return user


class ReactivateUser:
    def __init__(self, repository: UserRepository, event_bus: EventBus) -> None:
        self.repository = repository
        self.event_bus = event_bus

    async def execute(self, command: ChangeUserStatusCommand) -> User:
        user = await self.repository.get_by_id(command.user_id)
        if user is None:
            raise ResourceNotFoundError("El usuario no existe.")
        await ensure_can_manage_user(self.repository, command.actor_id, target=user)
        if user.is_active:
            raise InvalidStateError("El usuario ya esta activo.")
        user.activate()
        await self.repository.update(user)
        await self.event_bus.publish(
            UserReactivated(
                actor_id=command.actor_id,
                aggregate_type="user",
                aggregate_id=user.id,
                action="reactivated",
                data={"email": user.email.value},
            )
        )
        return user
