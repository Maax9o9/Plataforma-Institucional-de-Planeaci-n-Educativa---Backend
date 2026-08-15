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
        record = await self.refresh_tokens.consume(
            token=command.refresh_token,
            token_id=claims.token_id,
        )
        if record is None:
            raise AuthenticationError("El refresh token no es valido.")
        if not record.active:
            await self.refresh_tokens.revoke_session(record.session_id)
            raise AuthenticationError("Se detecto el reuso de un refresh token.")

        user = await self.repository.get_by_id(record.user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("El usuario no esta disponible.")

        refresh = self.token_service.issue_refresh(user, record.session_id)
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
