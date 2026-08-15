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
        indicator_items = []
        for indicator in indicators:
            captures = await self.captures.list_by_indicator(indicator.id)
            indicator_items.append(
                {
                    "tipo": "indicador",
                    "indicador_id": indicator.id,
                    "clave": indicator.key,
                    "capturas_validadas": len(captures),
                }
            )
        activities = await self.poa.list_activities(area_id=area_id)
        poa_items = []
        for activity in activities:
            advances = await self.advances.list_by_activity(activity.id)
            poa_items.append(
                {
                    "tipo": "poa_actividad",
                    "actividad_id": activity.id,
                    "descripcion": activity.description,
                    "avances_validados": sum(
                        advance.status.value == "validado" for advance in advances
                    ),
                }
            )
        return {
            "rol": role,
            "resumen": {
                "indicadores": len(indicator_items),
                "actividades_poa": len(poa_items),
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
        from sqlalchemy import func, select

        from app.modules.indicators_capture.infrastructure.models import CaptureModel
        from app.modules.indicators_catalog.infrastructure.models import IndicatorModel
        from app.modules.poa_planning.infrastructure.models import PoaActivityModel
        from app.modules.poa_tracking.infrastructure.models import PoaAdvanceModel

        area_id = filters.get("area_id")
        if role == "responsable_area":
            area_id = user.area_id
        async with self.session_factory() as session:
            indicator_statement = select(
                IndicatorModel.id,
                IndicatorModel.clave,
                func.count(CaptureModel.id).label("capturas_validadas"),
            ).outerjoin(
                CaptureModel,
                (CaptureModel.indicador_id == IndicatorModel.id)
                & (CaptureModel.estado == "validado"),
            ).group_by(IndicatorModel.id, IndicatorModel.clave)
            if area_id is not None:
                indicator_statement = indicator_statement.where(IndicatorModel.area_id == area_id)
            indicators = [
                {
                    "tipo": "indicador",
                    "indicador_id": row.id,
                    "clave": row.clave,
                    "capturas_validadas": row.capturas_validadas,
                }
                for row in (await session.execute(indicator_statement)).all()
            ]
            poa_statement = select(
                PoaActivityModel.id,
                PoaActivityModel.descripcion,
                func.count(PoaAdvanceModel.id).label("avances_validados"),
            ).outerjoin(
                PoaAdvanceModel,
                (PoaAdvanceModel.actividad_id == PoaActivityModel.id)
                & (PoaAdvanceModel.estado == "validado"),
            ).group_by(PoaActivityModel.id, PoaActivityModel.descripcion)
            poa = [
                {
                    "tipo": "poa_actividad",
                    "actividad_id": row.id,
                    "descripcion": row.descripcion,
                    "avances_validados": row.avances_validados,
                }
                for row in (await session.execute(poa_statement)).all()
            ]
            return {
                "rol": role,
                "resumen": {"indicadores": len(indicators), "actividades_poa": len(poa)},
                "indicadores": indicators,
                "poa": poa,
                "enlaces": {
                    "capturas_pendientes": "/api/v1/capturas/mis-pendientes",
                    "reportes_indicadores": "/api/v1/reportes/institucional",
                    "reportes_poa": "/api/v1/poa/reportes/ejecutivo",
                },
            }
