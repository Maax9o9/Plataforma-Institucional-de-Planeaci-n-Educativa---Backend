"""Consultas de reportes de indicadores y registro de generaciones."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.modules.evidence_management.domain.value_objects import FlowEntity


@dataclass(frozen=True)
class ReportResult:
    report_type: str
    filters: dict
    rows: list[dict]


def _restricted_area(filters: dict, current_user) -> tuple[int | None, bool]:
    area_id = filters.get("area_id")
    if current_user.has_any_role({"responsable_area", "consulta"}):
        area_id = current_user.area_id
        return area_id, area_id is None
    return area_id, False


def _instrument_name(report_type: str) -> str | None:
    return {"pide": "PIDE", "seaes": "SEAES", "cocodi": "COCODI"}.get(report_type)


def _row(indicator, capture=None, goal=None) -> dict:
    return {
        "indicador_id": indicator.id,
        "clave": getattr(indicator, "key", getattr(indicator, "clave", None)),
        "nombre": getattr(indicator, "name", getattr(indicator, "nombre", None)),
        "area_id": indicator.area_id,
        "responsable_id": getattr(
            indicator, "responsible_id", getattr(indicator, "responsable_id", None)
        ),
        "periodo_id": getattr(capture, "period_id", getattr(capture, "periodo_id", None)),
        "meta": getattr(goal, "value", getattr(goal, "valor", None)),
        "resultado": getattr(capture, "result", getattr(capture, "resultado", None)),
        "porcentaje_avance": getattr(
            capture, "progress_percentage", getattr(capture, "pct_avance", None)
        ),
        "semaforo": getattr(capture, "semaphore", getattr(capture, "semaforo", None)),
        "estado": getattr(
            getattr(capture, "status", None),
            "value",
            getattr(capture, "estado", None),
        ),
    }


class InMemoryIndicatorReportService:
    def __init__(self, indicators, captures, instruments=None, evidences=None) -> None:
        self.indicators = indicators
        self.captures = captures
        self.instruments = instruments
        self.evidences = evidences

    async def generate(self, report_type: str, filters: dict, current_user) -> ReportResult:
        indicators = await self.indicators.list(active_only=False)
        area_id, deny = _restricted_area(filters, current_user)
        if deny:
            return ReportResult(report_type, filters, [])
        if area_id is not None:
            indicators = [item for item in indicators if item.area_id == area_id]
        if filters.get("responsable_id") is not None:
            indicators = [
                item
                for item in indicators
                if item.responsible_id == filters["responsable_id"]
            ]
        instrument_name = _instrument_name(report_type)
        if instrument_name and self.instruments is not None:
            instruments = await self.instruments.list(active_only=False)
            valid_ids = {
                item.id
                for item in instruments
                if item.code.upper() == instrument_name or item.name.upper() == instrument_name
            }
            indicators = [item for item in indicators if item.instrument_ids & valid_ids]

        period_id = filters.get("periodo_id")
        captures = await self.captures.list_all()
        rows = []
        for indicator in indicators:
            related = [item for item in captures if item.indicator_id == indicator.id]
            if period_id is not None:
                related = [item for item in related if item.period_id == period_id]
            if report_type == "sin_captura":
                if not any(item.status.value in {"enviado", "validado"} for item in related):
                    rows.append(_row(indicator))
                continue
            if report_type == "evidencias_faltantes":
                for capture in related:
                    if self.evidences is None or not await self.evidences.has_for(
                        FlowEntity.CAPTURE, capture.id
                    ):
                        goal = await self.indicators.get_goal(indicator.id, capture.period_id)
                        rows.append(_row(indicator, capture, goal))
                continue
            if report_type == "en_riesgo":
                related = [item for item in related if item.semaphore in {"amarillo", "rojo"}]
            if not related:
                rows.append(_row(indicator))
            for capture in related:
                goal = await self.indicators.get_goal(indicator.id, capture.period_id)
                rows.append(_row(indicator, capture, goal))
        return ReportResult(report_type=report_type, filters=filters, rows=rows)


class SqlAlchemyIndicatorReportService:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    async def generate(self, report_type: str, filters: dict, current_user) -> ReportResult:
        from sqlalchemy import and_, or_, select

        from app.modules.evidence_management.infrastructure.models import EvidenceLinkModel
        from app.modules.indicators_capture.infrastructure.models import CaptureModel
        from app.modules.indicators_catalog.infrastructure.models import (
            GoalModel,
            IndicatorInstrumentModel,
            IndicatorModel,
        )
        from app.modules.institutional_catalogs.infrastructure.models import InstrumentModel

        area_id, deny = _restricted_area(filters, current_user)
        if deny:
            return ReportResult(report_type, filters, [])
        async with self.session_factory() as session:
            period_id = filters.get("periodo_id")
            capture_join = CaptureModel.indicador_id == IndicatorModel.id
            if period_id is not None:
                capture_join = and_(capture_join, CaptureModel.periodo_id == period_id)
            statement = (
                select(IndicatorModel, CaptureModel, GoalModel)
                .outerjoin(CaptureModel, capture_join)
                .outerjoin(
                    GoalModel,
                    and_(
                        GoalModel.indicador_id == IndicatorModel.id,
                        GoalModel.periodo_id == CaptureModel.periodo_id,
                    ),
                )
                .order_by(IndicatorModel.clave, CaptureModel.periodo_id)
            )
            instrument_name = _instrument_name(report_type)
            if instrument_name:
                instrument_ids = (
                    select(IndicatorInstrumentModel.c.indicador_id)
                    .join(
                        InstrumentModel,
                        InstrumentModel.id == IndicatorInstrumentModel.c.instrumento_id,
                    )
                    .where(
                        or_(
                            InstrumentModel.codigo.ilike(instrument_name),
                            InstrumentModel.nombre.ilike(instrument_name),
                        )
                    )
                )
                statement = statement.where(IndicatorModel.id.in_(instrument_ids))
            if area_id is not None:
                statement = statement.where(IndicatorModel.area_id == area_id)
            if filters.get("responsable_id") is not None:
                statement = statement.where(
                    IndicatorModel.responsable_id == filters["responsable_id"]
                )
            result = (await session.execute(statement)).all()
            linked_capture_ids = set(
                (
                    await session.scalars(
                        select(EvidenceLinkModel.entidad_id).where(
                            EvidenceLinkModel.entidad == "captura"
                        )
                    )
                ).all()
            )
            grouped: dict[int, tuple[object, list[tuple[object, object]]]] = {}
            for indicator, capture, goal in result:
                grouped.setdefault(indicator.id, (indicator, []))[1].append((capture, goal))
            rows = []
            for indicator, values in grouped.values():
                captures = [(capture, goal) for capture, goal in values if capture is not None]
                if report_type == "sin_captura":
                    completed = any(
                        capture.estado in {"enviado", "validado"}
                        for capture, _ in captures
                    )
                    if not completed:
                        rows.append(_row(indicator))
                    continue
                if report_type == "evidencias_faltantes":
                    rows.extend(
                        _row(indicator, capture, goal)
                        for capture, goal in captures
                        if capture.id not in linked_capture_ids
                    )
                    continue
                if report_type == "en_riesgo":
                    captures = [
                        (capture, goal)
                        for capture, goal in captures
                        if capture.semaforo in {"amarillo", "rojo"}
                    ]
                if not captures:
                    rows.append(_row(indicator))
                rows.extend(_row(indicator, capture, goal) for capture, goal in captures)
            return ReportResult(report_type=report_type, filters=filters, rows=rows)


class InMemoryReportLog:
    def __init__(self) -> None:
        self.items: list[dict] = []

    async def record(self, report: ReportResult, user_id: int, format_: str) -> None:
        self.items.append(
            {
                "usuario_id": user_id,
                "tipo": report.report_type,
                "parametros": report.filters,
                "formato": format_,
                "generado_en": datetime.now(UTC),
            }
        )
