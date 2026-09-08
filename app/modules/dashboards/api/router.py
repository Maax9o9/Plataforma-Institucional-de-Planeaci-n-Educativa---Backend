"""Dashboards de lectura por rol."""

from fastapi import APIRouter, Depends, Request

from app.core.security import require_roles

router = APIRouter(prefix="/dashboards", tags=["Dashboards"])


@router.get("/rectoria", summary="Consultar dashboard de Rectoria")
async def rectory_dashboard(
    request: Request,
    instrumento_id: int | None = None,
    area_id: int | None = None,
    periodo_id: int | None = None,
    current_user=Depends(require_roles("rectoria", "admin_sistema")),
):
    return await request.app.state.dashboard_service.get(
        "rectoria",
        current_user,
        {"instrumento_id": instrumento_id, "area_id": area_id, "periodo_id": periodo_id},
    )


@router.get("/planeacion", summary="Consultar dashboard de Planeacion")
async def planning_dashboard(
    request: Request,
    instrumento_id: int | None = None,
    area_id: int | None = None,
    periodo_id: int | None = None,
    current_user=Depends(require_roles("planeacion", "admin_sistema")),
):
    return await request.app.state.dashboard_service.get(
        "planeacion",
        current_user,
        {"instrumento_id": instrumento_id, "area_id": area_id, "periodo_id": periodo_id},
    )


@router.get("/mi-area", summary="Consultar dashboard de mi area")
async def area_dashboard(
    request: Request,
    current_user=Depends(require_roles("responsable_area", "capturista_poa")),
):
    return await request.app.state.dashboard_service.get(
        "responsable_area",
        current_user,
        {"area_id": current_user.area_id},
    )
