"""Consultas de reportes POA."""

from __future__ import annotations

from app.modules.indicators_reports.application.service import ReportResult


class InMemoryPoaReportService:
    def __init__(self, poa_repository, advance_repository) -> None:
        self.poa = poa_repository
        self.advances = advance_repository

    async def generate(self, report_type: str, filters: dict, current_user) -> ReportResult:
        activities = await self.poa.list_activities(area_id=filters.get("area_id"))
        rows: list[dict] = []
        missing_quarters: set[int] = set()
        for activity in activities:
            advances = await self.advances.list_by_activity(activity.id)
            if report_type == "anual":
                missing_quarters.update(
                    {1, 2, 3}
                    - {item.quarter for item in advances if item.status.value == "validado"}
                )
            for advance in advances:
                if (
                    filters.get("periodo_id") is not None
                    and advance.period_id != filters["periodo_id"]
                ):
                    continue
                if report_type == "estatus":
                    continue
                rows.append(
                    {
                        "actividad_id": activity.id,
                        "descripcion": activity.description,
                        "meta_anual": activity.annual_goal,
                        "cuatrimestre": advance.quarter,
                        "programado": advance.scheduled,
                        "alcanzado": advance.achieved,
                        "porcentaje_cumplimiento": advance.compliance_percentage,
                        "estado": advance.status.value,
                    }
                )
        if report_type == "estatus":
            rows = [
                {"actividad_id": activity.id, "descripcion": activity.description}
                for activity in activities
            ]
        result_filters = dict(filters)
        if report_type == "anual":
            result_filters["completo"] = not missing_quarters
            result_filters["cuatrimestres_faltantes"] = sorted(missing_quarters)
        return ReportResult(report_type=report_type, filters=result_filters, rows=rows)


class SqlAlchemyPoaReportService:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    async def generate(self, report_type: str, filters: dict, current_user) -> ReportResult:
        from sqlalchemy import select

        from app.modules.poa_planning.infrastructure.models import PoaActivityModel
        from app.modules.poa_tracking.infrastructure.models import PoaAdvanceModel

        async with self.session_factory() as session:
            statement = (
                select(PoaActivityModel, PoaAdvanceModel)
                .outerjoin(PoaAdvanceModel, PoaAdvanceModel.actividad_id == PoaActivityModel.id)
                .order_by(PoaActivityModel.id, PoaAdvanceModel.cuatrimestre)
            )
            if filters.get("periodo_id") is not None:
                statement = statement.where(PoaAdvanceModel.periodo_id == filters["periodo_id"])
            rows = []
            for activity, advance in (await session.execute(statement)).all():
                if advance is None:
                    continue
                rows.append(
                    {
                        "actividad_id": activity.id,
                        "descripcion": activity.descripcion,
                        "meta_anual": activity.meta_anual,
                        "cuatrimestre": advance.cuatrimestre,
                        "programado": advance.programado,
                        "alcanzado": advance.alcanzado,
                        "porcentaje_cumplimiento": advance.pct_cumplimiento,
                        "estado": advance.estado,
                    }
                )
            return ReportResult(report_type=report_type, filters=filters, rows=rows)
