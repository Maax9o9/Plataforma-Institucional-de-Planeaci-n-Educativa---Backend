"""Mapeo de errores internos a respuestas HTTP consistentes."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.modules.audit.domain.entities import AuditEntry
from app.shared.domain.exceptions import AppError, CaptureImmutableError

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
                        event_name="ImmutableEditBlocked",
                        aggregate_type=(
                            "poa_form" if "/poa/" in request.url.path else "capture"
                        ),
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
                "details": exc.details,
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
                "details": [
                    {"loc": error["loc"], "msg": error["msg"], "type": error["type"]}
                    for error in exc.errors()
                ],
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
            content={
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Ocurrio un error interno al procesar la solicitud.",
                "details": None,
                "request_id": request_id(request),
            },
        )
