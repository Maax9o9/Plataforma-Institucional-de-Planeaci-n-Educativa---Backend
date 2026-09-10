"""Mapeo de errores internos a respuestas HTTP consistentes."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as SQLTimeoutError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.modules.audit.domain.entities import AuditEntry
from app.shared.domain.exceptions import AppError, CaptureImmutableError

from .validation_messages import validation_detail

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    def request_id(request: Request) -> str | None:
        return getattr(request.state, "request_id", None)

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        if isinstance(exc, CaptureImmutableError):
            user = getattr(request.state, "current_user", None)
            try:
                await request.app.state.audit_repository.append(
                    AuditEntry(
                        id=uuid4(),
                        occurred_at=datetime.now(UTC),
                        actor_id=user.id if user else None,
                        actor_name=getattr(user, "full_name", None) if user else None,
                        event_name="ImmutableEditBlocked",
                        aggregate_type=("poa_form" if "/poa/" in request.url.path else "capture"),
                        aggregate_id=None,
                        action="edit_blocked",
                        data={"method": request.method, "path": request.url.path},
                    )
                )
            except Exception:
                logger.exception("No se pudo auditar el intento de edicion bloqueado")
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        if exc.status_code == 429 and isinstance(exc.details, dict):
            headers = {"Retry-After": str(exc.details.get("retry_after", 1))}
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code,
                "message": exc.message,
                "details": jsonable_encoder(exc.details),
                "request_id": request_id(request),
            },
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "code": "REQUEST_VALIDATION_ERROR",
                "message": "La solicitud contiene datos invalidos.",
                # No devolver el cuerpo original: puede contener contraseñas o tokens.
                "details": [validation_detail(error) for error in exc.errors()],
                "request_id": request_id(request),
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else "La solicitud no pudo procesarse."
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": "HTTP_ERROR",
                "message": detail,
                "details": None,
                "request_id": request_id(request),
            },
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "Error interno no controlado request_id=%s",
            request_id(request),
            exc_info=exc,
        )
        return JSONResponse(
            status_code=500,
            headers={"X-Request-ID": request_id(request) or ""},
            content={
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Ocurrio un error interno al procesar la solicitud.",
                "details": None,
                "request_id": request_id(request),
            },
        )

    @app.exception_handler(DBAPIError)
    @app.exception_handler(SQLTimeoutError)
    async def handle_database_error(request: Request, exc: Exception) -> JSONResponse:
        unavailable = isinstance(exc, (OperationalError, InterfaceError, SQLTimeoutError)) or (
            isinstance(exc, DBAPIError) and exc.connection_invalidated
        )
        if not unavailable:
            return await handle_unexpected_error(request, exc)
        logger.error("Base de datos no disponible request_id=%s", request_id(request), exc_info=exc)
        return JSONResponse(
            status_code=503,
            headers={"Retry-After": "5", "X-Request-ID": request_id(request) or ""},
            content={
                "code": "SERVICE_UNAVAILABLE",
                "message": "El servicio de datos no está disponible temporalmente. "
                "Conserve su captura y vuelva a intentarlo en unos momentos.",
                "details": {"retry_after": 5},
                "request_id": request_id(request),
            },
        )
