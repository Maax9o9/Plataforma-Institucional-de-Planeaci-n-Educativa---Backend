"""Editar datos de un usuario sin permitir eliminarlo."""

from __future__ import annotations

from app.shared.application.event_bus import EventBus
from app.shared.domain.exceptions import ConflictError, ResourceNotFoundError

from ...domain.entities import User
from ...domain.events import UserUpdated
from ...domain.ports.user_repository import UserRepository
from ..dto import UpdateUserCommand


class UpdateUser:
    def __init__(self, repository: UserRepository, event_bus: EventBus) -> None:
        self.repository = repository
        self.event_bus = event_bus

    async def execute(self, command: UpdateUserCommand) -> User:
        user = await self.repository.get_by_id(command.user_id)
        if user is None:
            raise ResourceNotFoundError("El usuario no existe.")
        if command.email is not None:
            existing = await self.repository.get_by_email(command.email)
            if existing is not None and existing.id != user.id:
                raise ConflictError("Ya existe un usuario con ese correo electronico.")

        user.update_details(
            email=command.email,
            full_name=command.full_name,
            roles=command.roles,
            area_id=command.area_id,
        )
        await self.repository.update(user)
        await self.event_bus.publish(
            UserUpdated(
                actor_id=command.actor_id,
                aggregate_type="user",
                aggregate_id=user.id,
                action="updated",
                data={"email": user.email.value, "roles": [role.value for role in user.roles]},
            )
        )
        return user
