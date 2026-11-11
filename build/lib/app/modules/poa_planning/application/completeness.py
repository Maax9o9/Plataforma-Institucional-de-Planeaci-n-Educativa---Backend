"""Una misma definición de captura completa para emisiones y recordatorios."""

from app.modules.evidence_management.domain.ports.repositories import EvidenceRepository
from app.modules.evidence_management.domain.value_objects import EvidenceType, FlowEntity

from ..domain.cedula_entities import PoaActivityFollowUp, PoaFormDetail


async def emission_errors(
    detail: PoaFormDetail, quarter: int, evidences: EvidenceRepository
) -> list[dict]:
    """Devuelve todos los pendientes corregibles, sin cambiar el estado de la cédula."""
    errors = []

    def add(field: str, message: str, **references) -> None:
        errors.append({"field": field, "message": message, **references})

    if not detail.form.strategy_type:
        add("tipo_estrategia", "Seleccione el tipo de estrategia.")
    if len(detail.form.signatories) != 2:
        add("firmantes", "Indique los nombres y cargos de los dos firmantes.")
    if not detail.indicators:
        add("indicadores", "Agregue al menos un indicador.")
    if not detail.activities:
        add("actividades", "Agregue al menos una actividad.")
    follow_ups = {
        item.form_activity_id: item for item in detail.follow_ups if item.quarter == quarter
    }
    for activity in detail.activities:
        follow_up = follow_ups.get(activity.id)
        refs = {"actividad_id": activity.id, "cuatrimestre": quarter}
        if follow_up is None:
            add("seguimiento", "Capture el seguimiento de esta actividad.", **refs)
            continue
        refs["seguimiento_id"] = follow_up.id
        if follow_up.achieved is None:
            add("alcanzado", "Ingrese el número alcanzado; cero es un valor válido.", **refs)
        for field, value in (("progreso", follow_up.progress), ("alcance", follow_up.scope)):
            if not value or not value.strip():
                add(field, f"Complete el campo {field}.", **refs)
        if not await has_file_evidence(evidences, follow_up.id):
            add("evidencias", "Vincule al menos una evidencia de tipo archivo.", **refs)
    if quarter == 3:
        for indicator in detail.indicators:
            for field, value in (
                ("total_alcanzado", indicator.total_achieved),
                ("porcentaje_alcanzado", indicator.achieved_percentage),
            ):
                if value is None:
                    add(
                        field,
                        f"Capture {field.replace('_', ' ')} del indicador.",
                        indicador_id=indicator.id,
                        cuatrimestre=3,
                    )
    return errors


async def has_file_evidence(evidences: EvidenceRepository, follow_up_id: int) -> bool:
    items = await evidences.list_for(FlowEntity.POA_FORM_FOLLOW_UP, follow_up_id)
    return any(item.evidence_type is EvidenceType.FILE for item in items)


async def is_follow_up_complete(
    follow_up: PoaActivityFollowUp | None, evidences: EvidenceRepository
) -> bool:
    return bool(
        follow_up is not None
        and follow_up.achieved is not None
        and follow_up.progress
        and follow_up.progress.strip()
        and follow_up.scope
        and follow_up.scope.strip()
        and await has_file_evidence(evidences, follow_up.id)
    )
