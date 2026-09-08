"""Consultas del POA actual a través de puertos, idénticas en memoria y PostgreSQL."""

from decimal import Decimal

from app.modules.evidence_management.domain.ports.repositories import EvidenceRepository
from app.modules.evidence_management.domain.value_objects import EvidenceType, FlowEntity
from app.modules.indicators_reports.application.service import ReportResult
from app.modules.institutional_catalogs.domain.ports.repositories import AreaRepository
from app.modules.poa_planning.application.access_control import can_edit_structure
from app.modules.poa_planning.domain.ports.cedula_repository import PoaFormRepository
from app.shared.application.actor import ActorContext
from app.shared.domain.exceptions import ForbiddenError


class PoaReportService:
    def __init__(
        self, forms: PoaFormRepository, evidences: EvidenceRepository, areas: AreaRepository
    ) -> None:
        self.forms = forms
        self.evidences = evidences
        self.areas = areas

    async def generate(self, report_type: str, filters: dict, current_user) -> ReportResult:
        actor = ActorContext.from_user(current_user)
        planning = await can_edit_structure(actor, self.areas)
        if not planning and (not actor.has_any_role("capturista_poa") or actor.area_id is None):
            raise ForbiddenError("El usuario no puede consultar reportes de cédulas POA.")
        area_id = filters.get("area_id") if planning else actor.area_id
        forms = await self.forms.list_forms(
            exercise_id=filters.get("ejercicio_id"),
            objective_number=filters.get("objetivo_numero"),
        )
        rows = []
        catalogs = {item.key: item for item in await self.forms.list_activity_catalog()}
        complete = True
        included_forms = 0
        for form in forms:
            if filters.get("cedula_id") is not None and form.id != filters["cedula_id"]:
                continue
            if filters.get("estrategia_clave") and form.strategy_key != filters["estrategia_clave"]:
                continue
            detail = await self.forms.get_detail(form.id)
            if detail is None:
                continue
            quarters = [
                q for q in detail.quarters if filters.get("periodo_id") in (None, q.period_id)
            ]
            if not quarters:
                continue
            activities = [
                a for a in detail.activities if area_id is None or a.executing_area_id == area_id
            ]
            if not activities:
                continue
            included_forms += 1
            issues = await self.forms.list_issues(form.id)
            emitted = {issue.quarter for issue in issues}
            complete = complete and emitted == {1, 2, 3}
            for activity in activities:
                catalog = catalogs.get(activity.activity_key)
                follow_ups = {
                    f.quarter: f for f in detail.follow_ups if f.form_activity_id == activity.id
                }
                base = {
                    "cedula_id": form.id,
                    "ejercicio_id": form.exercise_id,
                    "objetivo_numero": form.objective_number,
                    "estrategia_clave": form.strategy_key,
                    "area_responsable_id": form.responsible_area_id,
                    "area_ejecutora_id": activity.executing_area_id,
                    "actividad_id": activity.id,
                    "actividad_clave": activity.activity_key,
                    "descripcion": catalog.description if catalog else activity.activity_key,
                    "meta_anual": activity.annual_goal,
                }
                selected = [follow_ups[q.quarter] for q in quarters if q.quarter in follow_ups]
                if report_type in {"estatus", "dashboard"}:
                    scheduled = sum((f.scheduled or Decimal(0) for f in selected), Decimal(0))
                    achieved = sum((f.achieved or Decimal(0) for f in selected), Decimal(0))
                    kind = (
                        "cumplidas"
                        if achieved >= activity.annual_goal and selected
                        else "atrasadas"
                        if achieved < scheduled
                        else "pendientes"
                    )
                    if filters.get("tipo") and filters["tipo"] != kind:
                        continue
                    rows.append(
                        {
                            **base,
                            "programado": scheduled,
                            "alcanzado": achieved,
                            "estado": kind,
                            "cuatrimestres_capturados": len(selected),
                            "cuatrimestres_emitidos": len(
                                emitted.intersection(q.quarter for q in quarters)
                            ),
                        }
                    )
                    continue
                for quarter in quarters:
                    follow_up = follow_ups.get(quarter.quarter)
                    evidence_items = (
                        await self.evidences.list_for(FlowEntity.POA_FORM_FOLLOW_UP, follow_up.id)
                        if follow_up
                        else []
                    )
                    file_count = sum(e.evidence_type is EvidenceType.FILE for e in evidence_items)
                    if report_type == "evidencias_faltantes" and file_count:
                        continue
                    rows.append(
                        {
                            **base,
                            "cuatrimestre": quarter.quarter,
                            "periodo_id": quarter.period_id,
                            "seguimiento_id": follow_up.id if follow_up else None,
                            "programado": follow_up.scheduled if follow_up else None,
                            "alcanzado": follow_up.achieved if follow_up else None,
                            "progreso": follow_up.progress if follow_up else None,
                            "alcance": follow_up.scope if follow_up else None,
                            "justificacion_desviacion": (
                                follow_up.deviation_justification if follow_up else None
                            ),
                            "archivos_evidencia": file_count,
                            "estado": "capturado" if follow_up else "sin_captura",
                            "cedula_emitida": quarter.quarter in emitted,
                        }
                    )
        result_filters = {**filters, "fuente": "cedulas_actuales", "datos": "captura_actual"}
        if not planning:
            result_filters["area_id"] = actor.area_id
        if report_type == "anual":
            result_filters["completo"] = bool(included_forms) and complete
        return ReportResult(report_type, result_filters, rows)
