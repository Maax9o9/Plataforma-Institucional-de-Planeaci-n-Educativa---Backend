"""Configuracion central cargada desde variables de entorno."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Plataforma Institucional de Planeacion Educativa"
    environment: Literal["development", "testing", "staging", "production"] = "development"
    api_v1_prefix: str = "/api/v1"
    secret_key: SecretStr | None = None
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    refresh_cookie_name: str = Field(default="planeacion_refresh", pattern=r"^[A-Za-z0-9_-]+$")
    refresh_cookie_secure: bool = False
    refresh_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    database_echo: bool = False
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"]
    )
    cors_allow_all: bool = False
    database_url: str | None = None
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None
    email_provider: Literal["console", "smtp"] = "console"
    email_sender: str = "notificaciones@upchiapas.edu.mx"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: SecretStr | None = None
    smtp_start_tls: bool = True
    frontend_url: str = "http://localhost:3000"
    password_setup_expire_hours: int = 24
    upload_directory: str = "var/uploads"
    upload_max_bytes: int = 10 * 1024 * 1024
    reminder_check_interval_seconds: int = Field(default=6 * 60 * 60, ge=300)
    login_max_attempts: int = Field(default=5, ge=1, le=100)
    login_rate_limit_window_seconds: int = Field(default=60, ge=10, le=3600)


@lru_cache
def get_settings() -> Settings:
    return Settings()
