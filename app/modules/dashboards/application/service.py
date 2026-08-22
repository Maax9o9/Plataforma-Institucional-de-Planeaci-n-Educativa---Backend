"""Consultas agregadas de dashboards por rol."""

from __future__ import annotations


class InMemoryDashboardService:
    def __init__(self, indicators, captures, poa, advances) -> None:
        self.indicators = indicators
        self.captures = captures
        self.poa = poa
        self.advances = advances

    async def get(self, role: str, user, filters: dict) -> dict:
        area_id = filters.get("area_id")
        if role == "responsable_area":
            area_id = user.area_id
        indicators = await self.indicators.list(active_only=False)
        if area_id is not None:
            indicators = [item for item in indicators if item.area_id == area_id]
        if filters.get("instrumento_id") is not None:
            indicators = [
                item
                for item in indicators
                if filters["instrumento_id"] in item.instrument_ids
            ]
        indicator_items = []
        all_captures = await self.captures.list_all()
        for indicator in indicators:
            captures = [item for item in all_captures if item.indicator_id == indicator.id]
            if filters.get("periodo_id") is not None:
                captures = [
                    item for item in captures if item.period_id == filters["periodo_id"]
                ]
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
        activities = await self.poa.list_activities(area_id=area_id)
        poa_items = []
        for activity in activities:
            advances = await self.advances.list_by_activity(activity.id)
            if filters.get("periodo_id") is not None:
                advances = [
                    item for item in advances if item.period_id == filters["periodo_id"]
                ]
            states = {
                state: sum(advance.status.value == state for advance in advances)
                for state in ("borrador", "enviado", "validado", "rechazado")
            }
            poa_items.append(
                {
                    "tipo": "poa_actividad",
                    "actividad_id": activity.id,
                    "descripcion": activity.description,
                    "avances_validados": states["validado"],
                    "avances_por_estado": states,
                }
            )
        capture_totals = {
            state: sum(item["capturas_por_estado"][state] for item in indicator_items)
            for state in ("borrador", "enviado", "validado", "rechazado")
        }
        advance_totals = {
            state: sum(item["avances_por_estado"][state] for item in poa_items)
            for state in ("borrador", "enviado", "validado", "rechazado")
        }
        return {
            "rol": role,
            "resumen": {
                "indicadores": len(indicator_items),
                "actividades_poa": len(poa_items),
                "capturas_por_estado": capture_totals,
                "avances_poa_por_estado": advance_totals,
            },
            "indicadores": indicator_items,
            "poa": poa_items,
            "enlaces": {
                "capturas_pendientes": "/api/v1/capturas/mis-pendientes",
                "reportes_indicadores": "/api/v1/reportes/institucional",
                "reportes_poa": "/api/v1/poa/reportes/ejecutivo",
            },
        }


class SqlAlchemyDashboardService:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    async def get(self, role: str, user, filters: dict) -> dict:
        from sqlalchemy import and_, func, select

        from app.modules.indicators_capture.infrastructure.models import CaptureModel
        from app.modules.indicators_catalog.infrastructure.models import (
            IndicatorInstrumentModel,
            IndicatorModel,
        )
        from app.modules.poa_planning.infrastructure.models import (
            PoaActivityModel,
            PoaObjectiveModel,
            PoaProcessModel,
        )
        from app.modules.poa_tracking.infrastructure.models import PoaAdvanceModel

        area_id = filters.get("area_id")
        if role == "responsable_area":
            area_id = user.area_id
        async with self.session_factory() as session:
            capture_join = CaptureModel.indicador_id == IndicatorModel.id
            if filters.get("periodo_id") is not None:
                capture_join = and_(
                    capture_join, CaptureModel.periodo_id == filters["periodo_id"]
                )
            indicator_statement = select(
                IndicatorModel.id,
                IndicatorModel.clave,
                *(
                    func.count(CaptureModel.id)
                    .filter(CaptureModel.estado == state)
                    .label(state)
                    for state in ("borrador", "enviado", "validado", "rechazado")
                ),
            ).outerjoin(CaptureModel, capture_join).group_by(
                IndicatorModel.id, IndicatorModel.clave
            )
            if area_id is not None:
                indicator_statement = indicator_statement.where(IndicatorModel.area_id == area_id)
            if filters.get("instrumento_id") is not None:
                indicator_statement = indicator_statement.where(
                    IndicatorModel.id.in_(
                        select(IndicatorInstrumentModel.c.indicador_id).where(
                            IndicatorInstrumentModel.c.instrumento_id
                            == filters["instrumento_id"]
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
            advance_join = PoaAdvanceModel.actividad_id == PoaActivityModel.id
            if filters.get("periodo_id") is not None:
                advance_join = and_(
                    advance_join, PoaAdvanceModel.periodo_id == filters["periodo_id"]
                )
            poa_statement = select(
                PoaActivityModel.id,
                PoaActivityModel.descripcion,
                *(
                    func.count(PoaAdvanceModel.id)
                    .filter(PoaAdvanceModel.estado == state)
                    .label(state)
                    for state in ("borrador", "enviado", "validado", "rechazado")
                ),
            ).join(
                PoaObjectiveModel, PoaObjectiveModel.id == PoaActivityModel.objetivo_id
            ).join(
                PoaProcessModel, PoaProcessModel.id == PoaObjectiveModel.proceso_id
            ).outerjoin(PoaAdvanceModel, advance_join).group_by(
                PoaActivityModel.id, PoaActivityModel.descripcion
            )
            if area_id is not None:
                poa_statement = poa_statement.where(PoaProcessModel.area_id == area_id)
            poa = [
                {
                    "tipo": "poa_actividad",
                    "actividad_id": row.id,
                    "descripcion": row.descripcion,
                    "avances_validados": row.validado,
                    "avances_por_estado": {
                        state: getattr(row, state)
                        for state in ("borrador", "enviado", "validado", "rechazado")
                    },
                }
                for row in (await session.execute(poa_statement)).all()
            ]
            capture_totals = {
                state: sum(item["capturas_por_estado"][state] for item in indicators)
                for state in ("borrador", "enviado", "validado", "rechazado")
            }
            advance_totals = {
                state: sum(item["avances_por_estado"][state] for item in poa)
                for state in ("borrador", "enviado", "validado", "rechazado")
            }
            return {
                "rol": role,
                "resumen": {
                    "indicadores": len(indicators),
                    "actividades_poa": len(poa),
                    "capturas_por_estado": capture_totals,
                    "avances_poa_por_estado": advance_totals,
                },
                "indicadores": indicators,
                "poa": poa,
                "enlaces": {
                    "capturas_pendientes": "/api/v1/capturas/mis-pendientes",
                    "reportes_indicadores": "/api/v1/reportes/institucional",
                    "reportes_poa": "/api/v1/poa/reportes/ejecutivo",
                },
            }
