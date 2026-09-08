"""Reportes de las cédulas actuales; sin procesos ni avances del modelo retirado."""

from typing import Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.core.security import require_roles
from app.modules.indicators_reports.api.schemas import ReporteRespuesta
from app.modules.indicators_reports.application.exporters import export_xlsx
from app.shared.domain.exceptions import ValidationError

from ..application.exporters import export_pdf

router = APIRouter(prefix="/poa/reportes", tags=["Reportes de cédulas POA"])


def report_filters(
    request: Request,
    periodo_id: int | None = None,
    ejercicio_id: int | None = None,
    cedula_id: int | None = None,
    objetivo_numero: int | None = None,
    estrategia_clave: str | None = None,
    area_id: int | None = None,
    tipo: Literal["cumplidas", "pendientes", "atrasadas"] | None = None,
) -> dict:
    allowed = {
        "periodo_id",
        "ejercicio_id",
        "cedula_id",
        "objetivo_numero",
        "estrategia_clave",
        "area_id",
        "tipo",
        "formato",
    }
    if set(request.query_params) - allowed:
        raise ValidationError("Filtro no admitido por los reportes de cédulas POA.")
    return {
        "periodo_id": periodo_id,
        "ejercicio_id": ejercicio_id,
        "cedula_id": cedula_id,
        "objetivo_numero": objetivo_numero,
        "estrategia_clave": estrategia_clave,
        "area_id": area_id,
        "tipo": tipo,
    }


def _endpoint(report_type: str):
    async def generate(
        request: Request,
        filters: dict = Depends(report_filters),
        formato: Literal["json", "xlsx", "pdf"] = "json",
        current_user=Depends(require_roles("planeacion", "admin_sistema", "capturista_poa")),
    ):
        report = await request.app.state.poa_report_service.generate(
            report_type, filters, current_user
        )
        await request.app.state.report_log.record(report, current_user.id, formato)
        if formato == "json":
            return ReporteRespuesta(
                tipo=report.report_type, filtros=report.filters, filas=report.rows
            )
        content = export_xlsx(report) if formato == "xlsx" else export_pdf(report)
        media_type = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            if formato == "xlsx"
            else "application/pdf"
        )
        return StreamingResponse(
            content,
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="poa-{report_type}.{formato}"',
            },
        )

    generate.__name__ = f"report_poa_{report_type}"
    return generate


for _route, _kind in (
    ("cuatrimestral", "cuatrimestral"),
    ("anual", "anual"),
    ("por-cedula", "por_cedula"),
    ("por-area", "por_area"),
    ("estatus", "estatus"),
    ("evidencias-faltantes", "evidencias_faltantes"),
    ("ejecutivo", "ejecutivo"),
):
    router.add_api_route(
        f"/{_route}",
        _endpoint(_kind),
        methods=["GET"],
        response_model=ReporteRespuesta,
        summary=f"Reporte {_route} de cédulas POA",
    )
