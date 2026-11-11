"""Registrar un usuario institucional."""

from __future__ import annotations

from app.shared.application.event_bus import EventBus
from app.shared.domain.exceptions import ConflictError, ValidationError

from ...domain.entities import User
from ...domain.events import UserRegistered
from ...domain.ports.password_hasher import PasswordHasher
from ...domain.ports.user_repository import UserRepository
from ..dto import RegisterUserCommand


class CreateUser:
    def __init__(
        self,
        repository: UserRepository,
        password_hasher: PasswordHasher,
        event_bus: EventBus,
    ) -> None:
        self.repository = repository
        self.password_hasher = password_hasher
        self.event_bus = event_bus

    async def execute(self, command: RegisterUserCommand) -> User:
        if len(command.password) < 8:
            raise ValidationError("La contrasena debe tener al menos 8 caracteres.")
        if await self.repository.get_by_email(command.email):
            raise ConflictError("Ya existe un usuario con ese correo electronico.")

        user = User.register(
            email=command.email,
            full_name=command.full_name,
            password_hash=self.password_hasher.hash(command.password),
            roles=command.roles,
            area_id=command.area_id,
        )
        await self.repository.add(user)
        await self.event_bus.publish(
            UserRegistered(
                actor_id=command.actor_id,
                aggregate_type="user",
                aggregate_id=user.id,
                action="created",
                data={"email": user.email.value, "roles": [role.value for role in user.roles]},
            )
        )
        return user
