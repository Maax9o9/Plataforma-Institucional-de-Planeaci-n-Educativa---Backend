"""Entry point ASGI; la composición vive en ``core.app_factory``."""

from app.core.app_factory import app, create_app

__all__ = ["app", "create_app"]
