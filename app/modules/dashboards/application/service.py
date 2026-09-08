"""Consultas agregadas de dashboards por rol."""

from __future__ import annotations


class InMemoryDashboardService:
    def __init__(self, indicators, captures, poa_reports) -> None:
        self.indicators = indicators
        self.captures = captures
        self.poa_reports = poa_reports

    async def get(self, role: str, user, filters: dict) -> dict:
        area_id = filters.get("area_id")
        if role == "responsable_area":
            area_id = user.area_id
        indicators = await self.indicators.list(active_only=False)
        if area_id is not None:
            indicators = [item for item in indicators if item.area_id == area_id]
        if filters.get("instrumento_id") is not None:
            indicators = [
                item for item in indicators if filters["instrumento_id"] in item.instrument_ids
            ]
        indicator_items = []
        all_captures = await self.captures.list_all()
        for indicator in indicators:
            captures = [item for item in all_captures if item.indicator_id == indicator.id]
            if filters.get("periodo_id") is not None:
                captures = [item for item in captures if item.period_id == filters["periodo_id"]]
            states = {
                state: sum(item.status.value == state for item in captures)
                for state in ("borrador", "enviado", "validado", "rechazado")
            }
            indicator_items.append(
                {
                    "tipo": "indicador",
                    "indicador_id": indicator.id,
                    "clave": indicator.key,
                    "capturas_validadas": states["validado"],
                    "capturas_por_estado": states,
                }
            )
        return await _dashboard(role, user, filters, indicator_items, self.poa_reports)


class SqlAlchemyDashboardService:
    def __init__(self, session_factory, poa_reports) -> None:
        self.session_factory = session_factory
        self.poa_reports = poa_reports

    async def get(self, role: str, user, filters: dict) -> dict:
        from sqlalchemy import and_, func, select

        from app.modules.indicators_capture.infrastructure.models import CaptureModel
        from app.modules.indicators_catalog.infrastructure.models import (
            IndicatorInstrumentModel,
            IndicatorModel,
        )

        area_id = filters.get("area_id")
        if role == "responsable_area":
            area_id = user.area_id
        async with self.session_factory() as session:
            capture_join = CaptureModel.indicador_id == IndicatorModel.id
            if filters.get("periodo_id") is not None:
                capture_join = and_(capture_join, CaptureModel.periodo_id == filters["periodo_id"])
            indicator_statement = (
                select(
                    IndicatorModel.id,
                    IndicatorModel.clave,
                    *(
                        func.count(CaptureModel.id)
                        .filter(CaptureModel.estado == state)
                        .label(state)
                        for state in ("borrador", "enviado", "validado", "rechazado")
                    ),
                )
                .outerjoin(CaptureModel, capture_join)
                .group_by(IndicatorModel.id, IndicatorModel.clave)
            )
            if area_id is not None:
                indicator_statement = indicator_statement.where(IndicatorModel.area_id == area_id)
            if filters.get("instrumento_id") is not None:
                indicator_statement = indicator_statement.where(
                    IndicatorModel.id.in_(
                        select(IndicatorInstrumentModel.c.indicador_id).where(
                            IndicatorInstrumentModel.c.instrumento_id == filters["instrumento_id"]
                        )
                    )
                )
            indicators = [
                {
                    "tipo": "indicador",
                    "indicador_id": row.id,
                    "clave": row.clave,
                    "capturas_validadas": row.validado,
                    "capturas_por_estado": {
                        state: getattr(row, state)
                        for state in ("borrador", "enviado", "validado", "rechazado")
                    },
                }
                for row in (await session.execute(indicator_statement)).all()
            ]
            return await _dashboard(role, user, filters, indicators, self.poa_reports)


async def _dashboard(role, user, filters, indicators, poa_reports):
    from app.shared.domain.exceptions import ForbiddenError

    if role == "responsable_area" and user.area_id is None:
        indicators = []
    if not user.has_any_role({"admin_sistema", "planeacion", "rectoria", "responsable_area"}):
        indicators = []
    try:
        report = await poa_reports.generate("dashboard", filters, user)
        poa = report.rows
    except ForbiddenError:
        poa = []  # Consulta de Rectoría sobre nuevas cédulas aún no está habilitada.
    capture_totals = {
        state: sum(item["capturas_por_estado"][state] for item in indicators)
        for state in ("borrador", "enviado", "validado", "rechazado")
    }
    return {
        "rol": role,
        "resumen": {
            "indicadores": len(indicators),
            "actividades_poa": len(poa),
            "capturas_por_estado": capture_totals,
            "cedulas_poa": len({item["cedula_id"] for item in poa}),
            "seguimientos_poa_capturados": sum(item["cuatrimestres_capturados"] for item in poa),
        },
        "indicadores": indicators,
        "poa": poa,
        "enlaces": {
            "capturas_pendientes": "/api/v1/capturas/mis-pendientes",
            "reportes_indicadores": "/api/v1/reportes/institucional",
            "cedulas_poa": "/api/v1/poa/cedulas",
        },
    }
