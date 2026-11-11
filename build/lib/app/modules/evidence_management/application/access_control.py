"""Autorización de evidencias de indicadores y cédulas POA actuales."""

from app.modules.poa_planning.application.access_control import can_capture_activity
from app.shared.application.actor import ActorContext
from app.shared.domain.exceptions import ForbiddenError, InvalidStateError, ResourceNotFoundError

from ..domain.value_objects import FlowEntity


class EvidenceAccessControl:
    def __init__(self, evidences, captures, periods, poa_forms) -> None:
        self.evidences = evidences
        self.captures = captures
        self.periods = periods
        self.poa_forms = poa_forms

    async def ensure_target_viewable(self, entity: FlowEntity, entity_id: int, actor: ActorContext):
        if entity is FlowEntity.CAPTURE:
            item = await self.captures.get_by_id(entity_id)
            if item is None:
                raise ResourceNotFoundError("La captura no existe.")
            if not actor.is_planning and item.capturer_id != actor.id:
                raise ForbiddenError("El usuario no puede consultar esta captura.")
            return
        if entity is not FlowEntity.POA_FORM_FOLLOW_UP:
            raise ForbiddenError("El flujo POA anterior fue retirado.")
        follow_up = await self.poa_forms.get_follow_up(entity_id)
        if follow_up is None:
            raise ResourceNotFoundError("El seguimiento de la cédula no existe.")
        activity = await self.poa_forms.get_form_activity(follow_up.form_activity_id)
        if activity is None:
            raise ResourceNotFoundError("La actividad de la cédula no existe.")
        if not can_capture_activity(actor, activity.executing_area_id):
            raise ForbiddenError("La actividad POA no está asignada al área del usuario.")

    async def ensure_target_editable(self, entity: FlowEntity, entity_id: int, actor: ActorContext):
        await self.ensure_target_viewable(entity, entity_id, actor)
        item = (
            await self.captures.get_by_id(entity_id)
            if entity is FlowEntity.CAPTURE
            else await self.poa_forms.get_follow_up(entity_id)
        )
        period = await self.periods.get_by_id(item.period_id)
        is_open = period is not None and period.status.value == "abierto"
        if entity is FlowEntity.CAPTURE:
            item.ensure_editable(period_is_open=is_open)
        if not is_open:
            raise InvalidStateError("El periodo de la evidencia no está abierto.")

    async def ensure_can_view(self, evidence_id: int, actor: ActorContext):
        evidence = await self.evidences.get(evidence_id)
        if evidence is None:
            raise ResourceNotFoundError("La evidencia no existe.")
        links = await self.evidences.list_links(evidence_id)
        if not links and (actor.is_planning or evidence.uploaded_by == actor.id):
            return
        for link in links:
            try:
                await self.ensure_target_viewable(link.entity, link.entity_id, actor)
                return
            except (ForbiddenError, ResourceNotFoundError):
                continue
        raise ForbiddenError("La evidencia no pertenece a un registro actual autorizado.")

    async def ensure_can_replace(self, evidence_id: int, actor: ActorContext):
        await self.ensure_can_view(evidence_id, actor)
        for link in await self.evidences.list_links(evidence_id):
            await self.ensure_target_editable(link.entity, link.entity_id, actor)
