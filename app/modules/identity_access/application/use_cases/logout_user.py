"""Revocacion explicita de access y refresh tokens."""

from __future__ import annotations

from app.shared.application.event_bus import EventBus
from app.shared.domain.exceptions import AuthenticationError

from ...domain.events import UserLoggedOut
from ...domain.ports.refresh_token_repository import RefreshTokenStore
from ...domain.ports.revoked_token_repository import RevokedTokenStore
from ...domain.ports.token_service import TokenService
from ..dto import LogoutCommand


class LogoutUser:
    def __init__(
        self,
        token_service: TokenService,
        refresh_tokens: RefreshTokenStore,
        revoked_tokens: RevokedTokenStore,
        event_bus: EventBus,
    ) -> None:
        self.token_service = token_service
        self.refresh_tokens = refresh_tokens
        self.revoked_tokens = revoked_tokens
        self.event_bus = event_bus

    async def execute(self, command: LogoutCommand) -> None:
        refresh_claims = self.token_service.decode_refresh(command.refresh_token)
        if refresh_claims.subject != command.access_subject:
            raise AuthenticationError("Los tokens no pertenecen a la misma sesion.")
        await self.refresh_tokens.revoke(refresh_claims.token_id)
        await self.revoked_tokens.revoke(command.access_token_id, command.access_expires_at)
        await self.event_bus.publish(
            UserLoggedOut(
                actor_id=refresh_claims.subject,
                aggregate_type="user",
                aggregate_id=refresh_claims.subject,
                action="logout",
                data={"session_id": str(refresh_claims.session_id)},
            )
        )
