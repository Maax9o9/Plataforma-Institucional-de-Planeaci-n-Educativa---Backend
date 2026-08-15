"""Endpoints técnicos de disponibilidad."""

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

router = APIRouter(tags=["System"])


@router.get("/health", summary="Verificar disponibilidad de la API")
async def health(request: Request) -> dict[str, str]:
    settings = request.app.state.settings
    if request.app.state.db_session_factory is not None:
        try:
            async with request.app.state.db_session_factory() as session:
                await session.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            raise HTTPException(
                status_code=503,
                detail="La base de datos no esta disponible.",
            ) from exc
        return {"status": "ok", "environment": settings.environment, "database": "connected"}
    return {"status": "ok", "environment": settings.environment, "database": "in_memory"}
