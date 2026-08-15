"""Consultas de reportes de indicadores y registro de generaciones."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class ReportResult:
    report_type: str
    filters: dict
    rows: list[dict]


class InMemoryIndicatorReportService:
    def __init__(self, indicators, captures, instruments=None) -> None:
        self.indicators = indicators
        self.captures = captures
        self.instruments = instruments

    async def generate(self, report_type: str, filters: dict, current_user) -> ReportResult:
        indicators = await self.indicators.list(active_only=False)
        area_id = filters.get("area_id")
        if current_user.has_any_role({"responsable_area"}) and current_user.area_id is not None:
            area_id = current_user.area_id
        if area_id is not None:
            indicators = [item for item in indicators if item.area_id == area_id]
        instrument_filter = "PIDE" if report_type == "pide" else None
        if instrument_filter and self.instruments is not None:
            instruments = await self.instruments.list(active_only=False)
            valid_ids = {
                item.id
                for item in instruments
                if item.code.upper() == instrument_filter or item.name.upper() == instrument_filter
            }
            indicators = [item for item in indicators if item.instrument_ids & valid_ids]
        if report_type == "en_riesgo":
            captures = []
            for indicator in indicators:
                captures.extend(await self.captures.list_by_indicator(indicator.id))
            rows = [
                {
                    "indicador_id": item.indicator_id,
                    "periodo_id": item.period_id,
                    "porcentaje_avance": item.progress_percentage,
                    "semaforo": item.semaphore,
                }
                for item in captures
                if item.semaphore in {"amarillo", "rojo"}
            ]
        else:
            rows = [
                {
                    "indicador_id": item.id,
                    "clave": item.key,
                    "nombre": item.name,
                    "area_id": item.area_id,
                    "responsable_id": item.responsible_id,
                    "activo": item.is_active,
                }
                for item in indicators
            ]
        return ReportResult(report_type=report_type, filters=filters, rows=rows)


class SqlAlchemyIndicatorReportService:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    async def generate(self, report_type: str, filters: dict, current_user) -> ReportResult:
        from sqlalchemy import select

        from app.modules.indicators_capture.infrastructure.models import CaptureModel
        from app.modules.indicators_catalog.infrastructure.models import (
            IndicatorInstrumentModel,
            IndicatorModel,
        )
        from app.modules.institutional_catalogs.infrastructure.models import InstrumentModel

        async with self.session_factory() as session:
            statement = (
                select(IndicatorModel, CaptureModel)
                .outerjoin(CaptureModel, CaptureModel.indicador_id == IndicatorModel.id)
                .order_by(IndicatorModel.clave, CaptureModel.periodo_id)
            )
            instrument_filter = "PIDE" if report_type == "pide" else None
            if instrument_filter:
                instrument_ids = (
                    select(IndicatorInstrumentModel.c.indicador_id)
                    .join(
                        InstrumentModel,
                        InstrumentModel.id == IndicatorInstrumentModel.c.instrumento_id,
                    )
                    .where(InstrumentModel.nombre == instrument_filter)
                )
                statement = statement.where(IndicatorModel.id.in_(instrument_ids))
            area_id = filters.get("area_id")
            if current_user.has_any_role({"responsable_area"}) and current_user.area_id is not None:
                area_id = current_user.area_id
            if area_id is not None:
                statement = statement.where(IndicatorModel.area_id == area_id)
            if filters.get("periodo_id") is not None:
                statement = statement.where(CaptureModel.periodo_id == filters["periodo_id"])
            rows = []
            for indicator, capture in (await session.execute(statement)).all():
                if report_type == "en_riesgo" and (
                    capture is None or capture.semaforo not in {"amarillo", "rojo"}
                ):
                    continue
                rows.append(
                    {
                        "indicador_id": indicator.id,
                        "clave": indicator.clave,
                        "nombre": indicator.nombre,
                        "area_id": indicator.area_id,
                        "responsable_id": indicator.responsable_id,
                        "periodo_id": capture.periodo_id if capture else None,
                        "resultado": capture.resultado if capture else None,
                        "porcentaje_avance": capture.pct_avance if capture else None,
                        "semaforo": capture.semaforo if capture else None,
                        "estado": capture.estado if capture else None,
                    }
                )
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
