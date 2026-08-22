"""Consultas coherentes de reportes POA para memoria y PostgreSQL."""

from __future__ import annotations

from decimal import Decimal

from app.modules.evidence_management.domain.value_objects import FlowEntity
from app.modules.indicators_reports.application.service import ReportResult


def _area_scope(filters: dict, user) -> tuple[int | None, bool]:
    area_id = filters.get("area_id")
    if user.has_any_role({"responsable_area", "consulta"}):
        area_id = user.area_id
        return area_id, area_id is None
    return area_id, False


def _semaphore(value) -> str | None:
    if value is None:
        return None
    if value >= 90:
        return "verde"
    if value >= 40:
        return "amarillo"
    return "rojo"


def _row(activity, advance, process) -> dict:
    return {
        "actividad_id": activity.id,
        "descripcion": getattr(activity, "description", getattr(activity, "descripcion", None)),
        "meta_anual": getattr(activity, "annual_goal", getattr(activity, "meta_anual", None)),
        "responsable_id": getattr(
            activity, "responsible_id", getattr(activity, "responsable_id", None)
        ),
        "proceso_id": process.id,
        "area_id": process.area_id,
        "cuatrimestre": getattr(advance, "quarter", getattr(advance, "cuatrimestre", None)),
        "periodo_id": getattr(advance, "period_id", getattr(advance, "periodo_id", None)),
        "programado": getattr(advance, "scheduled", getattr(advance, "programado", None)),
        "alcanzado": getattr(advance, "achieved", getattr(advance, "alcanzado", None)),
        "porcentaje_cumplimiento": getattr(
            advance, "compliance_percentage", getattr(advance, "pct_cumplimiento", None)
        ),
        "semaforo": _semaphore(
            getattr(
                advance,
                "compliance_percentage",
                getattr(advance, "pct_cumplimiento", None),
            )
        ),
        "estado": getattr(
            getattr(advance, "status", None), "value", getattr(advance, "estado", None)
        ),
    }


def _status_row(activity, process, advances, kind: str) -> dict:
    validated = [
        item
        for item in advances
        if getattr(getattr(item, "status", None), "value", getattr(item, "estado", None))
        == "validado"
    ]
    scheduled = sum(
        (
            getattr(item, "scheduled", getattr(item, "programado", None)) or Decimal(0)
            for item in validated
        ),
        Decimal(0),
    )
    achieved = sum(
        (
            getattr(item, "achieved", getattr(item, "alcanzado", None)) or Decimal(0)
            for item in validated
        ),
        Decimal(0),
    )
    annual_goal = getattr(activity, "annual_goal", getattr(activity, "meta_anual", None))
    percentage = achieved / annual_goal * Decimal(100) if annual_goal else None
    row = _row(activity, None, process)
    row.update(
        {
            "programado": scheduled,
            "alcanzado": achieved,
            "porcentaje_cumplimiento": percentage,
            "semaforo": _semaphore(percentage),
            "estado": kind,
        }
    )
    return row


def _matches_status(report_type: str, filters: dict, activity, advances) -> bool:
    if report_type != "estatus":
        return True
    validated = [item for item in advances if item.status.value == "validado"]
    achieved = sum((item.achieved or Decimal(0) for item in validated), Decimal(0))
    scheduled = sum((item.scheduled or Decimal(0) for item in validated), Decimal(0))
    kind = filters.get("tipo", "pendientes")
    if kind == "cumplidas":
        return achieved >= activity.annual_goal
    if kind == "atrasadas":
        return bool(validated) and achieved < scheduled
    return not validated or achieved < activity.annual_goal


class InMemoryPoaReportService:
    def __init__(self, poa_repository, advance_repository, evidence_repository=None) -> None:
        self.poa = poa_repository
        self.advances = advance_repository
        self.evidences = evidence_repository

    async def generate(self, report_type: str, filters: dict, current_user) -> ReportResult:
        area_id, deny = _area_scope(filters, current_user)
        if deny:
            return ReportResult(report_type, filters, [])
        activities = await self.poa.list_activities(area_id=area_id)
        rows = []
        incomplete = False
        for activity in activities:
            objective = await self.poa.get_objective(activity.objective_id)
            process = await self.poa.get_process(objective.process_id) if objective else None
            if process is None:
                continue
            if filters.get("objetivo_id") is not None and objective.id != filters["objetivo_id"]:
                continue
            if filters.get("proceso_id") is not None and process.id != filters["proceso_id"]:
                continue
            if (
                filters.get("ejercicio_id") is not None
                and process.exercise_id != filters["ejercicio_id"]
            ):
                continue
            if (
                filters.get("responsable_id") is not None
                and activity.responsible_id != filters["responsable_id"]
            ):
                continue
            advances = await self.advances.list_by_activity(activity.id)
            if filters.get("periodo_id") is not None:
                advances = [
                    item for item in advances if item.period_id == filters["periodo_id"]
                ]
            if not _matches_status(report_type, filters, activity, advances):
                continue
            validated_quarters = {
                item.quarter for item in advances if item.status.value == "validado"
            }
            incomplete = incomplete or validated_quarters != {1, 2, 3}
            if report_type == "estatus":
                rows.append(
                    _status_row(
                        activity,
                        process,
                        advances,
                        filters.get("tipo", "pendientes"),
                    )
                )
                continue
            for advance in advances:
                if report_type == "evidencias_faltantes" and self.evidences is not None:
                    if await self.evidences.has_for(FlowEntity.POA_ADVANCE, advance.id):
                        continue
                rows.append(_row(activity, advance, process))
        result_filters = dict(filters)
        if report_type == "anual":
            result_filters["completo"] = not incomplete
        if report_type == "ejecutivo":
            values = [row["porcentaje_cumplimiento"] for row in rows]
            values = [Decimal(value) for value in values if value is not None]
            result_filters["cumplimiento_global"] = (
                sum(values, Decimal(0)) / len(values) if values else None
            )
        return ReportResult(report_type, result_filters, rows)


class SqlAlchemyPoaReportService:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    async def generate(self, report_type: str, filters: dict, current_user) -> ReportResult:
        from sqlalchemy import select

        from app.modules.evidence_management.infrastructure.models import EvidenceLinkModel
        from app.modules.poa_planning.infrastructure.models import (
            PoaActivityModel,
            PoaExerciseModel,
            PoaObjectiveModel,
            PoaProcessModel,
        )
        from app.modules.poa_tracking.infrastructure.models import PoaAdvanceModel

        area_id, deny = _area_scope(filters, current_user)
        if deny:
            return ReportResult(report_type, filters, [])
        async with self.session_factory() as session:
            statement = (
                select(
                    PoaActivityModel,
                    PoaObjectiveModel,
                    PoaProcessModel,
                    PoaExerciseModel,
                    PoaAdvanceModel,
                )
                .join(PoaObjectiveModel, PoaObjectiveModel.id == PoaActivityModel.objetivo_id)
                .join(PoaProcessModel, PoaProcessModel.id == PoaObjectiveModel.proceso_id)
                .join(PoaExerciseModel, PoaExerciseModel.id == PoaProcessModel.ejercicio_id)
                .outerjoin(
                    PoaAdvanceModel, PoaAdvanceModel.actividad_id == PoaActivityModel.id
                )
                .order_by(PoaActivityModel.id, PoaAdvanceModel.cuatrimestre)
            )
            if area_id is not None:
                statement = statement.where(PoaProcessModel.area_id == area_id)
            if filters.get("proceso_id") is not None:
                statement = statement.where(PoaProcessModel.id == filters["proceso_id"])
            if filters.get("ejercicio_id") is not None:
                statement = statement.where(PoaExerciseModel.id == filters["ejercicio_id"])
            if filters.get("objetivo_id") is not None:
                statement = statement.where(PoaObjectiveModel.id == filters["objetivo_id"])
            if filters.get("responsable_id") is not None:
                statement = statement.where(
                    PoaActivityModel.responsable_id == filters["responsable_id"]
                )
            if filters.get("periodo_id") is not None:
                statement = statement.where(PoaAdvanceModel.periodo_id == filters["periodo_id"])
            linked_ids = set(
                (
                    await session.scalars(
                        select(EvidenceLinkModel.entidad_id).where(
                            EvidenceLinkModel.entidad == "poa_avance"
                        )
                    )
                ).all()
            )
            grouped = {}
            for activity, objective, process, exercise, advance in (
                await session.execute(statement)
            ).all():
                entry = grouped.setdefault(activity.id, (activity, process, []))
                if advance is not None:
                    entry[2].append(advance)
            rows = []
            incomplete = False
            for activity, process, advances in grouped.values():
                validated = [item for item in advances if item.estado == "validado"]
                achieved = sum((item.alcanzado or 0 for item in validated), 0)
                scheduled = sum((item.programado or 0 for item in validated), 0)
                kind = filters.get("tipo", "pendientes")
                if report_type == "estatus":
                    matches = (
                        (kind == "cumplidas" and achieved >= activity.meta_anual)
                        or (kind == "atrasadas" and bool(validated) and achieved < scheduled)
                        or (
                            kind == "pendientes"
                            and (not validated or achieved < activity.meta_anual)
                        )
                    )
                    if matches:
                        rows.append(_status_row(activity, process, advances, kind))
                    continue
                incomplete = incomplete or {item.cuatrimestre for item in validated} != {1, 2, 3}
                for advance in advances:
                    if report_type == "evidencias_faltantes" and advance.id in linked_ids:
                        continue
                    rows.append(_row(activity, advance, process))
            result_filters = dict(filters)
            if report_type == "anual":
                result_filters["completo"] = not incomplete
            if report_type == "ejecutivo":
                values = [row["porcentaje_cumplimiento"] for row in rows]
                values = [Decimal(value) for value in values if value is not None]
                result_filters["cumplimiento_global"] = (
                    sum(values, Decimal(0)) / len(values) if values else None
                )
            return ReportResult(report_type, result_filters, rows)
