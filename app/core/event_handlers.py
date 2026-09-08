"""Suscripciones de eventos del composition root."""

from __future__ import annotations

from app.modules.audit.infrastructure.subscriber import register_audit_subscriber
from app.modules.indicators_capture.domain.events import CaptureCreated, CaptureSent
from app.modules.indicators_capture.domain.value_objects import CaptureStatus
from app.modules.indicators_scoring.application.dto import CalculateEvaluationCommand
from app.modules.indicators_scoring.application.use_cases.calculate_evaluation import (
    CalculateEvaluation,
)
from app.modules.indicators_validation.domain.entities import StateChange
from app.modules.indicators_validation.domain.events import CaptureValidated
from app.modules.notifications.application.service import NotificationService
from app.shared.application.event_bus import EventBus

from .container import Resources


def register_event_handlers(event_bus: EventBus, resources: Resources, email_sender):
    register_audit_subscriber(event_bus, resources.audit_repository)
    notification_service = NotificationService(
        resources.notification_repository,
        resources.user_repository,
        email_sender,
        resources.indicator_repository,
        resources.poa_period_recipients,
    )
    notification_service.register(event_bus)

    evaluation = CalculateEvaluation(
        indicators=resources.indicator_repository,
        captures=resources.capture_repository,
        goals=resources.indicator_repository,
        config=resources.threshold_config_repository,
        event_bus=event_bus,
    )

    async def calculate_after_validation(event: CaptureValidated) -> None:
        await evaluation.execute(
            CalculateEvaluationCommand(
                capture_id=int(event.data["capture_id"]),
                indicator_id=int(event.data["indicator_id"]),
                period_id=int(event.data["period_id"]),
            )
        )

    async def record_capture_created(event: CaptureCreated) -> None:
        await resources.state_change_repository.add(
            StateChange(
                entity_id=event.aggregate_id,
                from_status=None,
                to_status=CaptureStatus.DRAFT,
                user_id=event.actor_id,
                comment=None,
                created_at=event.occurred_at,
            )
        )

    async def record_capture_sent(event: CaptureSent) -> None:
        await resources.state_change_repository.add(
            StateChange(
                entity_id=event.aggregate_id,
                from_status=CaptureStatus(event.data["from_status"]),
                to_status=CaptureStatus.SENT,
                user_id=event.actor_id,
                comment=None,
                created_at=event.occurred_at,
            )
        )

    event_bus.subscribe(CaptureValidated, calculate_after_validation)
    event_bus.subscribe(CaptureCreated, record_capture_created)
    event_bus.subscribe(CaptureSent, record_capture_sent)
    return notification_service
