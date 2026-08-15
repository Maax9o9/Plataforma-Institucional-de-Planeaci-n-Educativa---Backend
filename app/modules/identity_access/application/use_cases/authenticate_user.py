"""Autenticacion con access token corto y refresh token rotado."""

from __future__ import annotations

from uuid import uuid4

from app.shared.application.event_bus import EventBus
from app.shared.domain.exceptions import AuthenticationError

from ...domain.events import UserLoggedIn
from ...domain.ports.password_hasher import PasswordHasher
from ...domain.ports.refresh_token_repository import RefreshTokenStore
from ...domain.ports.token_service import TokenService
from ...domain.ports.user_repository import UserRepository
from ..dto import AuthTokens


class AuthenticateUser:
    def __init__(
        self,
        repository: UserRepository,
        password_hasher: PasswordHasher,
        token_service: TokenService,
        refresh_tokens: RefreshTokenStore,
        event_bus: EventBus,
        access_token_expire_seconds: int,
    ) -> None:
        self.repository = repository
        self.password_hasher = password_hasher
        self.token_service = token_service
        self.refresh_tokens = refresh_tokens
        self.event_bus = event_bus
        self.access_token_expire_seconds = access_token_expire_seconds

    async def execute(self, email: str, password: str) -> AuthTokens:
        user = await self.repository.get_by_email(email)
        if user is not None and user.password_setup_required:
            raise AuthenticationError(
                "Debes configurar tu contrasena usando el enlace enviado por correo."
            )
        if (
            user is None
            or not user.is_active
            or not self.password_hasher.verify(password, user.password_hash)
        ):
            raise AuthenticationError("Correo o contrasena incorrectos.")

        session_id = uuid4()
        refresh = self.token_service.issue_refresh(user, session_id)
        await self.refresh_tokens.save(
            token=refresh.token,
            token_id=refresh.token_id,
            user_id=user.id,
            session_id=refresh.session_id,
            expires_at=refresh.expires_at,
        )
        await self.event_bus.publish(
            UserLoggedIn(
                actor_id=user.id,
                aggregate_type="user",
                aggregate_id=user.id,
                action="login",
                data={"session_id": str(session_id)},
            )
        )
        return AuthTokens(
            access_token=self.token_service.issue_access(user),
            refresh_token=refresh.token,
            token_type="bearer",
            expires_in=self.access_token_expire_seconds,
        )
