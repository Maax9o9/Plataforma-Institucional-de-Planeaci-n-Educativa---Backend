"""Destinatarios del periodo exacto de una cédula, no de todo el ejercicio."""

from dataclasses import dataclass

from app.modules.evidence_management.domain.ports.repositories import EvidenceRepository
from app.modules.identity_access.domain.ports.user_repository import UserReader
from app.modules.institutional_catalogs.domain.ports.repositories import AreaRepository
from app.shared.application.actor import ActorContext

from ..domain.ports.cedula_repository import PoaFormRepository
from .access_control import can_capture_activity, can_edit_structure
from .completeness import is_follow_up_complete


@dataclass(frozen=True)
class PoaPendingCapture:
    entity: str
    entity_id: int
    recipient_ids: frozenset[int]
    message: str


class PoaPeriodRecipients:
    def __init__(
        self,
        forms: PoaFormRepository,
        users: UserReader,
        areas: AreaRepository | None = None,
        evidences: EvidenceRepository | None = None,
    ) -> None:
        self.forms = forms
        self.users = users
        self.areas = areas
        self.evidences = evidences

    async def for_assignment(self, area_id: int) -> set[int]:
        """Sólo cuentas activas del área asignada con permiso de captura."""
        return {
            user.id
            for user in await self.users.list(active_only=True)
            if user.area_id == area_id
            and can_capture_activity(ActorContext.from_user(user), area_id)
        }

    async def pending_for_period(self, period_id: int) -> list[PoaPendingCapture]:
        if self.areas is None or self.evidences is None:
            return []
        users = await self.users.list(active_only=True)
        planning_ids = frozenset(
            [
                user.id
                for user in users
                if await can_edit_structure(ActorContext.from_user(user), self.areas)
            ]
        )
        pending = []
        for form in await self.forms.list_forms():
            quarters = await self.forms.list_form_quarters(form.id)
            schedule = next((q for q in quarters if q.period_id == period_id), None)
            if schedule is None:
                continue
            detail = await self.forms.get_detail(form.id)
            if detail is None:
                continue
            follow_ups = {
                f.form_activity_id: f
                for f in detail.follow_ups
                if f.quarter == schedule.quarter and f.period_id == period_id
            }
            for activity in detail.activities:
                if await is_follow_up_complete(follow_ups.get(activity.id), self.evidences):
                    continue
                recipients = frozenset(
                    u.id
                    for u in users
                    if activity.executing_area_id is not None
                    and u.area_id == activity.executing_area_id
                    and can_capture_activity(ActorContext.from_user(u), activity.executing_area_id)
                )
                pending.append(
                    PoaPendingCapture(
                        entity="poa_form_activity",
                        entity_id=activity.id,
                        recipient_ids=recipients,
                        message=(
                            f"Cédula {form.id}, actividad {activity.activity_key}, "
                            f"cuatrimestre {schedule.quarter}: falta completar alcanzado, "
                            "progreso, alcance o evidencia."
                        ),
                    )
                )
            if schedule.quarter == 3:
                for indicator in detail.indicators:
                    if (
                        indicator.total_achieved is not None
                        and indicator.achieved_percentage is not None
                    ):
                        continue
                    pending.append(
                        PoaPendingCapture(
                            entity="poa_form_indicator",
                            entity_id=indicator.id,
                            recipient_ids=planning_ids,
                            message=(
                                f"Cédula {form.id}, indicador {indicator.indicator_key}: "
                                "Planeación debe capturar número y porcentaje total alcanzado "
                                "en el tercer cuatrimestre."
                            ),
                        )
                    )
        return pending

    async def for_period(self, period_id: int) -> set[int]:
        area_ids = set()
        found = False
        for form in await self.forms.list_forms():
            quarters = await self.forms.list_form_quarters(form.id)
            if not any(q.period_id == period_id for q in quarters):
                continue
            found = True
            detail = await self.forms.get_detail(form.id)
            if detail:
                area_ids.update(a.executing_area_id for a in detail.activities)
        if not found:
            return set()
        recipients = set()
        for user in await self.users.list(active_only=True):
            actor = ActorContext.from_user(user)
            if actor.is_planning or any(can_capture_activity(actor, area) for area in area_ids):
                recipients.add(user.id)
        return recipients
