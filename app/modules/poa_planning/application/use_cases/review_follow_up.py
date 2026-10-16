"""Ciclo de revision del seguimiento cuatrimestral del POA (EP-08).

El area registra su avance, lo envia a revision, y Planeacion Educativa lo
valida o lo devuelve con un motivo. Es el flujo que la Direccion describio como
razon de ser del modulo y que el modelo de cedulas no contemplaba: hasta ahora
el seguimiento se guardaba y la unica accion posterior era la emision, que es un
respaldo inmutable y no una validacion.

Se reutiliza deliberadamente el mismo ciclo y el mismo historial que la captura
de indicadores, para que las areas no tengan que aprender dos flujos distintos.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.modules.evidence_management.domain.value_objects import FlowEntity
from app.modules.indicators_capture.domain.value_objects import CaptureStatus
from app.modules.indicators_validation.domain.entities import StateChange
from app.shared.application.actor import ActorContext
from app.shared.application.event_bus import EventBus
from app.shared.domain.domain_event import DomainEvent
from app.shared.domain.exceptions import ForbiddenError, ResourceNotFoundError

from ...domain.cedula_entities import PoaActivityFollowUp
from ..access_control import can_capture_activity

#: Entidad con la que el seguimiento se registra en `cambios_estado`.
ENTITY = "poa_cedula_seguimiento"

#: Quien puede aprobar o devolver. `revisor_poa` existia en el enum y en el
#: directorio institucional sin conceder ninguna facultad; aqui la obtiene.
REVIEW_ROLES = ("planeacion", "planeacion_admin", "admin_sistema", "revisor_poa")


def _can_review(actor: ActorContext) -> bool:
    return actor.has_any_role(*REVIEW_ROLES)


@dataclass(frozen=True)
class ReviewFollowUpCommand:
    follow_up_id: int
    actor: ActorContext
    comment: str | None = None


class _BaseReview:
    def __init__(
        self,
        repository,
        state_changes,
        event_bus: EventBus,
        evidences=None,
        notifications=None,
    ) -> None:
        self.repository = repository
        self.state_changes = state_changes
        self.event_bus = event_bus
        self.evidences = evidences
        self.notifications = notifications

    async def _load(self, follow_up_id: int) -> PoaActivityFollowUp:
        item = await self.repository.get_follow_up(follow_up_id)
        if item is None:
            raise ResourceNotFoundError("El seguimiento no existe.")
        return item

    async def _activity_area(self, follow_up: PoaActivityFollowUp) -> int | None:
        activity = await self.repository.get_form_activity(follow_up.form_activity_id)
        return activity.executing_area_id if activity else None

    async def _record(
        self,
        item: PoaActivityFollowUp,
        previous: CaptureStatus,
        actor: ActorContext,
        comment: str | None,
    ) -> None:
        await self.repository.update_follow_up(item)
        await self.state_changes.add(StateChange(
            entity=ENTITY,
            entity_id=item.id,
            from_status=previous,
            to_status=item.status,
            user_id=actor.id,
            comment=comment,
            created_at=datetime.now(UTC),
        ))
        await self.event_bus.publish(DomainEvent(
            actor_id=actor.id,
            aggregate_type="poa_form_follow_up",
            aggregate_id=item.id,
            action=item.status.value,
            data={"quarter": item.quarter, "from_status": previous.value},
        ))

    async def _notify(self, item: PoaActivityFollowUp, mensaje: str) -> None:
        """Avisa a quien capturo. Nunca debe tumbar la revision."""
        if self.notifications is None:
            return
        from uuid import NAMESPACE_URL, uuid5

        try:
            await self.notifications.notify_user(
                user_id=item.captured_by,
                notification_type=(
                    "validacion" if item.status is CaptureStatus.VALIDATED else "rechazo"
                ),
                message=mensaje,
                entity="poa_cedula_seguimiento",
                entity_id=item.id,
                source_event_id=uuid5(
                    NAMESPACE_URL,
                    f"poa-follow-up:{item.id}:{item.status.value}:{item.updated_at.isoformat()}",
                ),
            )
        except Exception:  # noqa: BLE001 - la notificacion es un efecto secundario
            return


class SendPoaFollowUp(_BaseReview):
    """HU-08.01: el area manda su avance a revision."""

    async def execute(self, command: ReviewFollowUpCommand) -> PoaActivityFollowUp:
        item = await self._load(command.follow_up_id)
        area_id = await self._activity_area(item)
        if not can_capture_activity(command.actor, area_id):
            raise ForbiddenError("La actividad POA no está asignada al área del usuario.")

        has_evidence = True
        if self.evidences is not None:
            has_evidence = await self.evidences.has_for(FlowEntity.POA_FORM_FOLLOW_UP, item.id)

        previous = item.status
        item.send(has_evidence=has_evidence)
        await self._record(item, previous, command.actor, None)
        return item


class ValidatePoaFollowUp(_BaseReview):
    """HU-08.02: Planeacion aprueba el avance reportado."""

    async def execute(self, command: ReviewFollowUpCommand) -> PoaActivityFollowUp:
        if not _can_review(command.actor):
            raise ForbiddenError("Tu rol no permite validar seguimientos del POA.")
        item = await self._load(command.follow_up_id)
        if item.captured_by == command.actor.id and not command.actor.is_planning:
            raise ForbiddenError("No puedes validar tu propio seguimiento.")

        previous = item.status
        item.validate()
        await self._record(item, previous, command.actor, None)
        await self._notify(
            item,
            f"Tu seguimiento del cuatrimestre {item.quarter} fue validado.",
        )
        return item


class RejectPoaFollowUp(_BaseReview):
    """HU-08.02 y HU-08.03: se devuelve al area con el motivo visible."""

    async def execute(self, command: ReviewFollowUpCommand) -> PoaActivityFollowUp:
        if not _can_review(command.actor):
            raise ForbiddenError("Tu rol no permite rechazar seguimientos del POA.")
        item = await self._load(command.follow_up_id)

        previous = item.status
        item.reject(command.comment or "")
        await self._record(item, previous, command.actor, item.review_comment)
        await self._notify(
            item,
            f"Tu seguimiento del cuatrimestre {item.quarter} fue devuelto: {item.review_comment}",
        )
        return item
