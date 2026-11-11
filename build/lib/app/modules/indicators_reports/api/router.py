"""Endpoints de reportes de indicadores."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.core.security import require_roles

from ..application.exporters import export_pdf, export_xlsx
from .schemas import ReporteRespuesta

TAG = "Reportes de indicadores"
router = APIRouter(prefix="/reportes", tags=[TAG])
PLANNING_ROLES = ("planeacion", "admin_sistema")
INSTRUMENT_ROLES = (*PLANNING_ROLES, "consulta")
INSTITUTIONAL_ROLES = (*PLANNING_ROLES, "rectoria", "consulta")
AREA_ROLES = (*PLANNING_ROLES, "responsable_area", "consulta")


async def _generate(
    request: Request,
    report_type: str,
    user,
    filters: dict,
    formato: Literal["json", "xlsx", "pdf"],
):
    report = await request.app.state.indicator_report_service.generate(report_type, filters, user)
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
        headers={"Content-Disposition": f'attachment; filename="{report_type}.{formato}"'},
    )


@router.get(
    "/pide",
    response_model=ReporteRespuesta,
    summary="Generar reporte PIDE",
)
async def report_pide(
    request: Request,
    periodo_id: int | None = None,
    formato: Literal["json", "xlsx", "pdf"] = "json",
    current_user=Depends(require_roles(*INSTRUMENT_ROLES)),
) -> ReporteRespuesta:
    return await _generate(request, "pide", current_user, {"periodo_id": periodo_id}, formato)


@router.get("/seaes", response_model=ReporteRespuesta, summary="Generar reporte SEAES")
async def report_seaes(
    request: Request,
    periodo_id: int | None = None,
    formato: Literal["json", "xlsx", "pdf"] = "json",
    current_user=Depends(require_roles(*INSTRUMENT_ROLES)),
) -> ReporteRespuesta:
    return await _generate(request, "seaes", current_user, {"periodo_id": periodo_id}, formato)


@router.get("/cocodi", response_model=ReporteRespuesta, summary="Generar reporte COCODI")
async def report_cocodi(
    request: Request,
    periodo_id: int | None = None,
    formato: Literal["json", "xlsx", "pdf"] = "json",
    current_user=Depends(require_roles(*INSTRUMENT_ROLES)),
) -> ReporteRespuesta:
    return await _generate(request, "cocodi", current_user, {"periodo_id": periodo_id}, formato)


@router.get(
    "/institucional",
    response_model=ReporteRespuesta,
    summary="Generar reporte institucional consolidado",
)
async def report_institutional(
    request: Request,
    periodo_id: int | None = None,
    formato: Literal["json", "xlsx", "pdf"] = "json",
    current_user=Depends(require_roles(*INSTITUTIONAL_ROLES)),
) -> ReporteRespuesta:
    return await _generate(
        request,
        "institucional",
        current_user,
        {"periodo_id": periodo_id},
        formato,
    )


@router.get(
    "/por-area",
    response_model=ReporteRespuesta,
    summary="Generar reporte por area",
)
async def report_by_area(
    request: Request,
    area_id: int | None = None,
    periodo_id: int | None = None,
    formato: Literal["json", "xlsx", "pdf"] = "json",
    current_user=Depends(require_roles(*AREA_ROLES)),
) -> ReporteRespuesta:
    return await _generate(
        request,
        "por_area",
        current_user,
        {"area_id": area_id, "periodo_id": periodo_id},
        formato,
    )


@router.get(
    "/por-responsable",
    response_model=ReporteRespuesta,
    summary="Generar reporte por responsable",
)
async def report_by_responsible(
    request: Request,
    responsable_id: int | None = None,
    area_id: int | None = None,
    formato: Literal["json", "xlsx", "pdf"] = "json",
    current_user=Depends(require_roles(*PLANNING_ROLES)),
) -> ReporteRespuesta:
    return await _generate(
        request,
        "por_responsable",
        current_user,
        {"area_id": area_id, "responsable_id": responsable_id},
        formato,
    )


@router.get(
    "/por-periodo/{periodo_id}",
    response_model=ReporteRespuesta,
    summary="Generar reporte por periodo",
)
async def report_by_period(
    periodo_id: int,
    request: Request,
    formato: Literal["json", "xlsx", "pdf"] = "json",
    current_user=Depends(require_roles(*PLANNING_ROLES)),
) -> ReporteRespuesta:
    return await _generate(
        request,
        "por_periodo",
        current_user,
        {"periodo_id": periodo_id},
        formato,
    )


@router.get(
    "/en-riesgo",
    response_model=ReporteRespuesta,
    summary="Generar reporte de indicadores en riesgo",
)
async def report_at_risk(
    request: Request,
    area_id: int | None = None,
    periodo_id: int | None = None,
    formato: Literal["json", "xlsx", "pdf"] = "json",
    current_user=Depends(require_roles(*INSTITUTIONAL_ROLES)),
) -> ReporteRespuesta:
    return await _generate(
        request,
        "en_riesgo",
        current_user,
        {"area_id": area_id, "periodo_id": periodo_id},
        formato,
    )


@router.get(
    "/sin-captura",
    response_model=ReporteRespuesta,
    summary="Consultar indicadores sin captura",
)
async def report_without_capture(
    request: Request,
    periodo_id: int | None = None,
    formato: Literal["json", "xlsx", "pdf"] = "json",
    current_user=Depends(require_roles(*PLANNING_ROLES)),
) -> ReporteRespuesta:
    return await _generate(
        request,
        "sin_captura",
        current_user,
        {"periodo_id": periodo_id},
        formato,
    )


@router.get(
    "/evidencias-faltantes",
    response_model=ReporteRespuesta,
    summary="Consultar capturas sin evidencia",
)
async def report_missing_evidence(
    request: Request,
    periodo_id: int | None = None,
    formato: Literal["json", "xlsx", "pdf"] = "json",
    current_user=Depends(require_roles(*PLANNING_ROLES)),
) -> ReporteRespuesta:
    return await _generate(
        request,
        "evidencias_faltantes",
        current_user,
        {"periodo_id": periodo_id},
        formato,
    )
