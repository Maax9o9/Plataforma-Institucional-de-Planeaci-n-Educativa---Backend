"""Factory de FastAPI: configura recursos, middleware y rutas."""

from __future__ import annotations

import secrets
from dataclasses import fields

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import SecretStr

from app.api.router_registry import include_api_routers
from app.api.system_router import router as system_router
from app.core.config import Settings, get_settings
from app.core.container import Resources, create_resources
from app.core.cors import build_cors_options
from app.core.event_handlers import register_event_handlers
from app.core.exceptions import register_exception_handlers
from app.core.lifecycle import lifespan
from app.core.logging import configure_logging
from app.core.middleware import RequestIdMiddleware, SecurityHeadersMiddleware
from app.core.openapi import custom_openapi
from app.modules.identity_access.infrastructure.security import (
    Argon2PasswordHasher,
    JwtTokenService,
)
from app.shared.infrastructure.email.factory import create_email_sender
from app.shared.infrastructure.events.in_memory_event_bus import InMemoryEventBus


def _validate_security_settings(settings: Settings) -> None:
    if settings.secret_key is None:
        if settings.environment == "production":
            raise RuntimeError("SECRET_KEY debe estar configurada en produccion.")
        settings.secret_key = SecretStr(secrets.token_urlsafe(32))
    elif settings.environment == "production" and len(settings.secret_key.get_secret_value()) < 32:
        raise RuntimeError("SECRET_KEY debe tener al menos 32 caracteres en produccion.")


def _bind_resources(app: FastAPI, resources: Resources) -> None:
    for resource in fields(resources):
        setattr(app.state, resource.name, getattr(resources, resource.name))
    app.state.password_hasher = Argon2PasswordHasher()
    app.state.token_service = JwtTokenService(app.state.settings)
    app.state.email_sender = create_email_sender(app.state.settings)


def create_app(settings: Settings | None = None) -> FastAPI:
    configure_logging()
    settings = settings or get_settings()
    _validate_security_settings(settings)
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description=(
            "API de la Plataforma Institucional de Planeacion Educativa. "
            "Usa SQLAlchemy async cuando DATABASE_URL esta configurada y memoria "
            "como fallback local."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.event_bus = InMemoryEventBus()
    resources = create_resources(settings)
    _bind_resources(app, resources)
    app.state.notification_service = register_event_handlers(
        app.state.event_bus,
        resources,
        app.state.email_sender,
    )
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CORSMiddleware, **build_cors_options(settings))
    register_exception_handlers(app)
    app.include_router(system_router)
    include_api_routers(app, settings.api_v1_prefix)
    app.openapi = lambda: custom_openapi(app)
    return app


app = create_app()
