"""Destinatarios del periodo exacto de una cédula, no de todo el ejercicio."""

from app.modules.identity_access.domain.ports.user_repository import UserReader
from app.shared.application.actor import ActorContext

from ..domain.ports.cedula_repository import PoaFormRepository
from .access_control import can_capture_activity


class PoaPeriodRecipients:
    def __init__(self, forms: PoaFormRepository, users: UserReader) -> None:
        self.forms = forms
        self.users = users

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
