"""Mapeo de errores internos a respuestas HTTP consistentes."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.shared.domain.exceptions import AppError


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message, "details": exc.details},
            headers={"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "code": "REQUEST_VALIDATION_ERROR",
                "message": "La solicitud contiene datos invalidos.",
                "details": exc.errors(),
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else "La solicitud no pudo procesarse."
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": "HTTP_ERROR", "message": detail, "details": None},
            headers=exc.headers,
        )
