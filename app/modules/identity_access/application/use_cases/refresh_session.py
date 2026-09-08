"""Rotacion de refresh tokens y deteccion de reuso."""

from __future__ import annotations

from app.shared.application.event_bus import EventBus
from app.shared.domain.exceptions import AuthenticationError

from ...domain.events import UserLoggedIn
from ...domain.ports.refresh_token_repository import RefreshTokenStore
from ...domain.ports.token_service import TokenService
from ...domain.ports.user_repository import UserRepository
from ..dto import AuthTokens, RefreshCommand


class RefreshSession:
    def __init__(
        self,
        repository: UserRepository,
        token_service: TokenService,
        refresh_tokens: RefreshTokenStore,
        event_bus: EventBus,
        access_token_expire_seconds: int,
    ) -> None:
        self.repository = repository
        self.token_service = token_service
        self.refresh_tokens = refresh_tokens
        self.event_bus = event_bus
        self.access_token_expire_seconds = access_token_expire_seconds

    async def execute(self, command: RefreshCommand) -> AuthTokens:
        claims = self.token_service.decode_refresh(command.refresh_token)
        user = await self.repository.get_by_id(claims.subject)
        if user is None or not user.is_active:
            raise AuthenticationError("El usuario no esta disponible.")
        if claims.password_version != user.password_version:
            raise AuthenticationError("La contraseña cambió. Inicia sesión nuevamente.")

        refresh = self.token_service.issue_refresh(user, claims.session_id)
        record = await self.refresh_tokens.rotate(
            current_token=command.refresh_token,
            current_token_id=claims.token_id,
            new_token=refresh.token,
            new_token_id=refresh.token_id,
            user_id=user.id,
            session_id=refresh.session_id,
            expires_at=refresh.expires_at,
        )
        if record is None:
            raise AuthenticationError("El refresh token no es valido.")
        if (
            not record.active
            or record.user_id != claims.subject
            or record.session_id != claims.session_id
        ):
            await self.refresh_tokens.revoke_session(claims.session_id)
            raise AuthenticationError("Se detecto el reuso de un refresh token.")
        await self.event_bus.publish(
            UserLoggedIn(
                actor_id=user.id,
                aggregate_type="user",
                aggregate_id=user.id,
                action="refresh",
                data={"session_id": str(record.session_id)},
            )
        )
        return AuthTokens(
            access_token=self.token_service.issue_access(user),
            refresh_token=refresh.token,
            token_type="bearer",
            expires_in=self.access_token_expire_seconds,
        )
