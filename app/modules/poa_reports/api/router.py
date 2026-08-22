"""Reportes del POA."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.core.security import require_roles
from app.modules.indicators_reports.api.schemas import ReporteRespuesta
from app.modules.indicators_reports.application.exporters import export_pdf, export_xlsx

TAG = "Reportes POA"
router = APIRouter(prefix="/poa/reportes", tags=[TAG])
PLANNING_ROLES = ("planeacion", "admin_sistema")
EXECUTIVE_ROLES = (*PLANNING_ROLES, "rectoria")
AREA_STATUS_ROLES = (*PLANNING_ROLES, "responsable_area")


async def _generate(request: Request, report_type: str, user, filters: dict, formato: str):
    report = await request.app.state.poa_report_service.generate(report_type, filters, user)
    await request.app.state.report_log.record(report, user.id, formato)
    if formato == "json":
        return ReporteRespuesta(tipo=report.report_type, filtros=report.filters, filas=report.rows)
    content = export_xlsx(report) if formato == "xlsx" else export_pdf(report)
    media_type = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if formato == "xlsx"
        else "application/pdf"
    )
    return StreamingResponse(
        content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="poa-{report_type}.{formato}"'},
    )


@router.get(
    "/cuatrimestral", response_model=ReporteRespuesta, summary="Generar reporte cuatrimestral POA"
)
async def report_quarterly(
    request: Request,
    periodo_id: int | None = None,
    proceso_id: int | None = None,
    area_id: int | None = None,
    objetivo_id: int | None = None,
    formato: Literal["json", "xlsx", "pdf"] = "json",
    current_user=Depends(require_roles(*PLANNING_ROLES)),
):
    return await _generate(
        request,
        "cuatrimestral",
        current_user,
        {
            "periodo_id": periodo_id,
            "proceso_id": proceso_id,
            "area_id": area_id,
            "objetivo_id": objetivo_id,
        },
        formato,
    )


@router.get("/anual", response_model=ReporteRespuesta, summary="Generar reporte anual POA")
async def report_annual(
    request: Request,
    ejercicio_id: int | None = None,
    formato: Literal["json", "xlsx", "pdf"] = "json",
    current_user=Depends(require_roles(*EXECUTIVE_ROLES)),
):
    return await _generate(request, "anual", current_user, {"ejercicio_id": ejercicio_id}, formato)


@router.get(
    "/por-proceso", response_model=ReporteRespuesta, summary="Generar reporte POA por proceso"
)
async def report_by_process(
    request: Request,
    proceso_id: int | None = None,
    formato: Literal["json", "xlsx", "pdf"] = "json",
    current_user=Depends(require_roles(*PLANNING_ROLES)),
):
    return await _generate(
        request, "por_proceso", current_user, {"proceso_id": proceso_id}, formato
    )


@router.get("/por-area", response_model=ReporteRespuesta, summary="Generar reporte POA por area")
async def report_by_area(
    request: Request,
    area_id: int | None = None,
    formato: Literal["json", "xlsx", "pdf"] = "json",
    current_user=Depends(require_roles(*PLANNING_ROLES)),
):
    return await _generate(request, "por_area", current_user, {"area_id": area_id}, formato)


@router.get(
    "/estatus", response_model=ReporteRespuesta, summary="Consultar estatus de actividades POA"
)
async def report_status(
    request: Request,
    tipo: Literal["cumplidas", "pendientes", "atrasadas"] = "pendientes",
    area_id: int | None = None,
    proceso_id: int | None = None,
    responsable_id: int | None = None,
    formato: Literal["json", "xlsx", "pdf"] = "json",
    current_user=Depends(require_roles(*AREA_STATUS_ROLES)),
):
    return await _generate(
        request,
        "estatus",
        current_user,
        {
            "tipo": tipo,
            "area_id": area_id,
            "proceso_id": proceso_id,
            "responsable_id": responsable_id,
        },
        formato,
    )


@router.get(
    "/evidencias-faltantes",
    response_model=ReporteRespuesta,
    summary="Consultar evidencias faltantes del POA",
)
async def report_missing_evidence(
    request: Request,
    periodo_id: int | None = None,
    formato: Literal["json", "xlsx", "pdf"] = "json",
    current_user=Depends(require_roles(*PLANNING_ROLES)),
):
    return await _generate(
        request, "evidencias_faltantes", current_user, {"periodo_id": periodo_id}, formato
    )


@router.get(
    "/ejecutivo",
    response_model=ReporteRespuesta,
    summary="Generar reporte ejecutivo institucional POA",
)
async def report_executive(
    request: Request,
    ejercicio_id: int | None = None,
    formato: Literal["json", "xlsx", "pdf"] = "json",
    current_user=Depends(require_roles(*EXECUTIVE_ROLES)),
):
    return await _generate(
        request, "ejecutivo", current_user, {"ejercicio_id": ejercicio_id}, formato
    )
