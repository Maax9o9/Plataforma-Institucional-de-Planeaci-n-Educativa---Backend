"""Cambio privado de contraseña de la cuenta administrativa autenticada."""

from app.shared.application.event_bus import EventBus
from app.shared.domain.exceptions import AuthenticationError, ForbiddenError, ValidationError

from ...domain.events import UserPasswordChanged
from ...domain.ports.password_hasher import PasswordHasher
from ...domain.ports.refresh_token_repository import RefreshTokenStore
from ...domain.ports.user_repository import UserRepository


class ChangeAdminPassword:
    def __init__(
        self,
        users: UserRepository,
        hasher: PasswordHasher,
        refresh_tokens: RefreshTokenStore,
        events: EventBus,
        unit_of_work,
    ) -> None:
        self.users = users
        self.hasher = hasher
        self.refresh_tokens = refresh_tokens
        self.events = events
        self.unit_of_work = unit_of_work

    async def execute(self, user_id: int, current_password: str, new_password: str) -> None:
        if not 8 <= len(new_password) <= 128:
            raise ValidationError("La contraseña nueva debe tener entre 8 y 128 caracteres.")
        async with self.unit_of_work():
            user = await self.users.get_by_id(user_id)
            if user is None or not user.is_active:
                raise AuthenticationError("El usuario no está disponible.")
            if not user.has_any_role({"admin_sistema", "planeacion_admin"}):
                raise ForbiddenError("Este cambio requiere una cuenta administrativa.")
            if not self.hasher.verify(current_password, user.password_hash):
                raise AuthenticationError("La contraseña actual es incorrecta.")
            if current_password == new_password:
                raise ValidationError("La contraseña nueva debe ser diferente de la actual.")
            user.password_hash = self.hasher.hash(new_password)
            user.password_version += 1
            user.password_setup_required = False
            user.touch()
            await self.users.update(user)
            await self.refresh_tokens.revoke_user(user.id)
            await self.events.publish(
                UserPasswordChanged(
                    actor_id=user.id,
                    aggregate_type="user",
                    aggregate_id=user.id,
                    action="password_changed",
                    data={},
                )
            )
