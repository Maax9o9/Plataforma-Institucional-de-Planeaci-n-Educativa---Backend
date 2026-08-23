"""Invitacion administrada y configuracion inicial de contrasena."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from app.core.config import Settings
from app.shared.application.event_bus import EventBus
from app.shared.application.ports.email_sender import EmailSender
from app.shared.domain.exceptions import AuthenticationError, ResourceNotFoundError, ValidationError

from ...domain.entities import User
from ...domain.events import UserRegistered
from ...domain.ports.password_hasher import PasswordHasher
from ...domain.ports.password_setup_repository import PasswordSetupTokenStore
from ...domain.ports.refresh_token_repository import RefreshTokenStore
from ...domain.ports.user_repository import UserRepository
from ..dto import RegisterUserCommand


class InviteUser:
    def __init__(
        self,
        repository: UserRepository,
        password_hasher: PasswordHasher,
        token_store: PasswordSetupTokenStore,
        email_sender: EmailSender,
        event_bus: EventBus,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.password_hasher = password_hasher
        self.token_store = token_store
        self.email_sender = email_sender
        self.event_bus = event_bus
        self.settings = settings

    async def execute(self, command: RegisterUserCommand) -> User:
        if await self.repository.get_by_email(command.email):
            from app.shared.domain.exceptions import ConflictError

            raise ConflictError("Ya existe un usuario con ese correo electronico.")
        user = User.register(
            email=command.email,
            full_name=command.full_name,
            password_hash=self.password_hasher.hash(secrets.token_urlsafe(32)),
            roles=command.roles,
            area_id=command.area_id,
        )
        user.password_setup_required = True
        await self.repository.add(user)
        raw_token = secrets.token_urlsafe(32)
        token_hash = sha256(raw_token.encode("utf-8")).hexdigest()
        expires_at = datetime.now(UTC) + timedelta(
            hours=self.settings.password_setup_expire_hours
        )
        await self.token_store.issue(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        link = (
            f"{self.settings.frontend_url.rstrip('/')}/establecer-contrasena"
            f"?token={raw_token}"
        )
        await self.email_sender.send(
            user.email.value,
            "Configura tu acceso a la Plataforma de Planeacion",
            (
                f"<p>Hola {user.full_name},</p>"
                f"<p>Configura tu contrasena desde este enlace:</p>"
                f"<p><a href=\"{link}\">Crear contrasena</a></p>"
                f"<p>El enlace expira en {self.settings.password_setup_expire_hours} horas.</p>"
            ),
            f"Configura tu contrasena: {link}",
        )
        await self.event_bus.publish(
            UserRegistered(
                actor_id=command.actor_id,
                aggregate_type="user",
                aggregate_id=user.id,
                action="invited",
                data={"email": user.email.value},
            )
        )
        return user


class SetInitialPassword:
    def __init__(
        self,
        repository: UserRepository,
        password_hasher: PasswordHasher,
        token_store: PasswordSetupTokenStore,
        refresh_tokens: RefreshTokenStore,
    ) -> None:
        self.repository = repository
        self.password_hasher = password_hasher
        self.token_store = token_store
        self.refresh_tokens = refresh_tokens

    async def validate_token(self, raw_token: str) -> bool:
        return await self.token_store.is_valid(self._hash(raw_token))

    async def execute(self, raw_token: str, password: str) -> None:
        if len(password) < 8:
            raise ValidationError("La contrasena debe tener al menos 8 caracteres.")
        user_id = await self.token_store.consume(self._hash(raw_token))
        if user_id is None:
            raise AuthenticationError("El enlace no existe, ya fue usado o expiro.")
        user = await self.repository.get_by_id(user_id)
        if user is None:
            raise ResourceNotFoundError("El usuario asociado al enlace no existe.")
        user.password_hash = self.password_hasher.hash(password)
        user.password_setup_required = False
        user.touch()
        await self.repository.update(user)
        await self.refresh_tokens.revoke_user(user.id)

    @staticmethod
    def _hash(raw_token: str) -> str:
        return sha256(raw_token.encode("utf-8")).hexdigest()
