"""Reportes de las cédulas actuales; sin procesos ni avances del modelo retirado."""

from io import BytesIO
from typing import Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.core.authorization import actor_from_user
from app.core.security import require_roles
from app.modules.indicators_reports.api.schemas import ReporteRespuesta
from app.modules.indicators_reports.application.exporters import export_xlsx
from app.shared.domain.exceptions import ValidationError

from ..application.exporters import export_pdf
from ..application.sep_export import MEDIA_TYPE as SEP_MEDIA_TYPE
from ..application.sep_export import ExportarFormatoSep

router = APIRouter(prefix="/poa/reportes", tags=["Reportes de cédulas POA"])


def report_filters(
    request: Request,
    periodo_id: int | None = None,
    #: El cuatrimestre del POA (1, 2 o 3), no el periodo.
    #:
    #: Cada cédula abre sus propios tres periodos, así que `periodo_id`
    #: identifica el cuatrimestre *de una sola cédula* y no sirve para
    #: preguntar «cómo va el primer cuatrimestre del ejercicio», que es la
    #: pregunta que trae a alguien a los reportes. El tablero ya filtra así.
    cuatrimestre: int | None = None,
    ejercicio_id: int | None = None,
    cedula_id: int | None = None,
    objetivo_numero: int | None = None,
    estrategia_clave: str | None = None,
    area_id: int | None = None,
    tipo: Literal["cumplidas", "pendientes", "atrasadas"] | None = None,
) -> dict:
    allowed = {
        "periodo_id",
        "cuatrimestre",
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
    if cuatrimestre is not None and cuatrimestre not in (1, 2, 3):
        raise ValidationError("El cuatrimestre del POA es 1, 2 o 3.")
    return {
        "periodo_id": periodo_id,
        "cuatrimestre": cuatrimestre,
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
        current_user=Depends(
            require_roles("planeacion", "admin_sistema", "capturista_poa", "rectoria")
        ),
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


@router.get(
    "/formato-sep",
    summary="Descargar el POA en el formato .xlsm de la SEP",
    response_class=StreamingResponse,
)
async def export_sep_format(
    request: Request,
    ejercicio_id: int,
    current_user=Depends(require_roles("planeacion", "admin_sistema", "rectoria")),
):
    """El entregable: la plantilla oficial rellenada con lo capturado.

    Lo que no cabe en el formato —un objetivo con más cédulas que bloques, una
    cédula con más actividades que huecos— viaja en una cabecera propia en vez
    de perderse: el archivo se descarga igual, y quien lo pidió se entera de
    que algo quedó fuera.
    """
    archivo, incidencias = await ExportarFormatoSep(
        request.app.state.poa_form_repository,
        request.app.state.poa_repository,
        request.app.state.area_repository,
    ).execute(exercise_id=ejercicio_id, actor=actor_from_user(current_user))

    cabeceras = {
        "Content-Disposition": f'attachment; filename="poa-formato-sep-{ejercicio_id}.xlsm"',
        "X-Incidencias": str(len(incidencias)),
    }
    if incidencias:
        # Las cabeceras HTTP no admiten saltos de línea ni acentos sin
        # codificar: se manda el detalle en una sola línea, ya escapada.
        cabeceras["X-Incidencias-Detalle"] = (
            " | ".join(incidencias).encode("ascii", "backslashreplace").decode("ascii")
        )
    return StreamingResponse(BytesIO(archivo), media_type=SEP_MEDIA_TYPE, headers=cabeceras)
