"""Composicion de casos de uso para FastAPI."""

from __future__ import annotations

from fastapi import Request

from ..application.use_cases.authenticate_user import AuthenticateUser
from ..application.use_cases.change_user_status import DeactivateUser, ReactivateUser
from ..application.use_cases.create_user import CreateUser
from ..application.use_cases.logout_user import LogoutUser
from ..application.use_cases.password_setup import InviteUser, SetInitialPassword
from ..application.use_cases.refresh_session import RefreshSession
from ..application.use_cases.update_user import UpdateUser


def get_create_user_use_case(request: Request) -> CreateUser:
    return CreateUser(
        repository=request.app.state.user_repository,
        password_hasher=request.app.state.password_hasher,
        event_bus=request.app.state.event_bus,
    )


def get_authenticate_user_use_case(request: Request) -> AuthenticateUser:
    settings = request.app.state.settings
    return AuthenticateUser(
        repository=request.app.state.user_repository,
        password_hasher=request.app.state.password_hasher,
        token_service=request.app.state.token_service,
        refresh_tokens=request.app.state.refresh_token_store,
        event_bus=request.app.state.event_bus,
        access_token_expire_seconds=settings.access_token_expire_minutes * 60,
    )


def get_refresh_session_use_case(request: Request) -> RefreshSession:
    settings = request.app.state.settings
    return RefreshSession(
        repository=request.app.state.user_repository,
        token_service=request.app.state.token_service,
        refresh_tokens=request.app.state.refresh_token_store,
        event_bus=request.app.state.event_bus,
        access_token_expire_seconds=settings.access_token_expire_minutes * 60,
    )


def get_logout_user_use_case(request: Request) -> LogoutUser:
    return LogoutUser(
        token_service=request.app.state.token_service,
        refresh_tokens=request.app.state.refresh_token_store,
        revoked_tokens=request.app.state.revoked_token_store,
        event_bus=request.app.state.event_bus,
    )


def get_update_user_use_case(request: Request) -> UpdateUser:
    return UpdateUser(request.app.state.user_repository, request.app.state.event_bus)


def get_deactivate_user_use_case(request: Request) -> DeactivateUser:
    return DeactivateUser(
        request.app.state.user_repository,
        request.app.state.refresh_token_store,
        request.app.state.event_bus,
    )


def get_reactivate_user_use_case(request: Request) -> ReactivateUser:
    return ReactivateUser(request.app.state.user_repository, request.app.state.event_bus)


def get_invite_user_use_case(request: Request) -> InviteUser:
    return InviteUser(
        request.app.state.user_repository,
        request.app.state.password_hasher,
        request.app.state.password_setup_token_store,
        request.app.state.email_sender,
        request.app.state.event_bus,
        request.app.state.settings,
    )


def get_set_initial_password_use_case(request: Request) -> SetInitialPassword:
    return SetInitialPassword(
        request.app.state.user_repository,
        request.app.state.password_hasher,
        request.app.state.password_setup_token_store,
    )
