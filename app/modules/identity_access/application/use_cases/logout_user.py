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
        session_id = None
        if command.refresh_token:
            try:
                refresh_claims = self.token_service.decode_refresh(command.refresh_token)
                if refresh_claims.subject == command.access_subject:
                    session_id = refresh_claims.session_id
                    await self.refresh_tokens.revoke_session(refresh_claims.session_id)
            except AuthenticationError:
                # Logout es idempotente: una cookie expirada o ya eliminada no impide
                # revocar el access token presentado por el usuario.
                pass
        await self.revoked_tokens.revoke(command.access_token_id, command.access_expires_at)
        await self.event_bus.publish(
            UserLoggedOut(
                actor_id=command.access_subject,
                aggregate_type="user",
                aggregate_id=command.access_subject,
                action="logout",
                data={"session_id": str(session_id) if session_id else None},
            )
        )
