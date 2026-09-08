from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.modules.evidence_management.domain.value_objects import EvidenceType
from app.modules.identity_access.domain.entities import User
from app.modules.identity_access.domain.value_objects import Role
from app.modules.notifications.application.reminders import GenerateReminders
from app.modules.notifications.application.service import NotificationService
from app.modules.notifications.domain.entities import Notification
from app.modules.notifications.infrastructure.repository import InMemoryNotificationRepository
from app.modules.poa_planning.application.access_control import PLANNING_AREA_NAME
from app.modules.poa_planning.application.period_recipients import PoaPeriodRecipients
from app.modules.poa_planning.domain.cedula_entities import PoaFormIndicator, PoaSignatory
from app.shared.domain.exceptions import ValidationError


def account(id_, role, area_id=None, active=True):
    user = User.register(
        email=f"test-{id_}-{uuid4().hex}@example.com",
        full_name="Test",
        password_hash="not-used",
        roles={role},
        area_id=area_id,
    )
    user.id = id_
    user.is_active = active
    return user


def pending_policy(quarter=1, follow_up=None, file=False, total=None):
    forms, users, areas, evidences = AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock()
    forms.list_forms.return_value = [SimpleNamespace(id=1)]
    forms.list_form_quarters.return_value = [SimpleNamespace(period_id=9, quarter=quarter)]
    forms.get_detail.return_value = SimpleNamespace(
        activities=[SimpleNamespace(id=10, activity_key="6.1.5", executing_area_id=2)],
        follow_ups=[] if follow_up is None else [follow_up],
        indicators=[
            SimpleNamespace(
                id=20, indicator_key="6.1.2", total_achieved=total, achieved_percentage=total
            )
        ],
    )
    users.list.return_value = [
        account(1, Role.CAPTURISTA_POA, 2),
        account(2, Role.CAPTURISTA_POA, 3),
        account(3, Role.REVISOR_POA, 2),
        account(4, Role.CAPTURISTA_POA, 2, active=False),
        account(5, Role.PLANEACION),
        account(6, Role.CAPTURISTA_POA, 7),
        account(7, Role.CONSULTA, 2),
    ]
    # UserReader.list(active_only=True) es el contrato de filtrado.
    users.list.return_value = [u for u in users.list.return_value if u.is_active]
    areas.get_by_id.side_effect = lambda id_: SimpleNamespace(
        is_active=True, name=PLANNING_AREA_NAME if id_ == 7 else "Otra área"
    )
    evidences.list_for.return_value = (
        [SimpleNamespace(evidence_type=EvidenceType.FILE)] if file else []
    )
    return PoaPeriodRecipients(forms, users, areas, evidences)


@pytest.mark.asyncio
async def test_pending_only_for_exact_area_and_totals_only_in_third_quarter():
    policy = pending_policy()
    assert await policy.for_assignment(2) == {1}
    assert await policy.pending_for_period(123) == []
    pending = await policy.pending_for_period(9)
    assert [(p.entity, p.recipient_ids) for p in pending] == [("poa_form_activity", {1})]
    pending = await pending_policy(quarter=3).pending_for_period(9)
    assert [(p.entity, p.recipient_ids) for p in pending] == [
        ("poa_form_activity", {1}),
        ("poa_form_indicator", {5, 6}),
    ]
    zero_total = await pending_policy(quarter=3, total=0).pending_for_period(9)
    assert len(zero_total) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", [None, "achieved", "progress", "scope", "file"])
async def test_complete_requires_evidence_and_zero_is_a_real_capture(missing):
    follow_up = SimpleNamespace(
        id=4,
        form_activity_id=10,
        quarter=1,
        period_id=9,
        achieved=Decimal(0),
        progress="Sin avance",
        scope="Sin cobertura",
    )
    if missing in {"achieved", "progress", "scope"}:
        setattr(follow_up, missing, None)
    policy = pending_policy(follow_up=follow_up, file=missing != "file")
    pending = await policy.pending_for_period(9)
    assert len(pending) == (0 if missing is None else 1)


@pytest.mark.asyncio
async def test_start_week_reminders_catch_up_and_do_not_repeat():
    policy = pending_policy(quarter=3)
    period = SimpleNamespace(
        id=9,
        starts_on=date(2035, 9, 1),
        ends_on=date(2035, 12, 31),
        status=SimpleNamespace(value="abierto"),
        period_type=SimpleNamespace(value="poa"),
    )
    periods = AsyncMock()
    periods.list.return_value = [period]
    notifications = InMemoryNotificationRepository()
    generator = GenerateReminders(periods, AsyncMock(), notifications, policy)
    assert await generator.execute(period.starts_on - timedelta(days=1)) == 0
    assert await generator.execute(period.starts_on) == 3
    assert await generator.execute(period.starts_on + timedelta(days=1)) == 3
    assert len(await notifications.list_for_user(1)) == 1
    assert len(await notifications.list_for_user(5)) == 1
    assert await generator.execute(period.ends_on - timedelta(days=8)) == 3
    assert len(await notifications.list_for_user(1)) == 1
    assert await generator.execute(period.ends_on - timedelta(days=7)) == 3
    assert len(await notifications.list_for_user(1)) == 2
    assert len(await notifications.list_for_user(5)) == 2
    assert await generator.execute(period.ends_on + timedelta(days=1)) == 0
    period.status.value = "cerrado"
    assert await generator.execute(period.ends_on) == 0
    # Recuperación de una caída: no necesita ejecutarse exactamente el día de apertura.
    fresh = InMemoryNotificationRepository()
    period.status.value = "borrador"
    await GenerateReminders(periods, AsyncMock(), fresh, policy).execute(date(2035, 9, 2))
    assert len(await fresh.list_for_user(1)) == 1


@pytest.mark.asyncio
async def test_notification_delivery_retry_and_atomic_claim(backend_client):
    app, _ = backend_client
    user = account(None, Role.PLANEACION)
    await app.state.user_repository.add(user)
    repository = app.state.notification_repository
    notification = await repository.create(
        Notification(
            user_id=user.id,
            notification_type="poa_total_inicio",
            message="Pendiente <dato>",
            entity="poa_form_indicator",
            entity_id=12,
            source_event_id=uuid4(),
        )
    )
    assert await repository.claim_email(notification.id)
    assert not await repository.claim_email(notification.id)
    await repository.release_email(notification.id)
    sender = AsyncMock()
    sender.send.side_effect = RuntimeError("SMTP temporalmente no disponible")
    service = NotificationService(repository, app.state.user_repository, sender)
    await service._send_email(notification, user.email.value)
    assert not (await repository.list_for_user(user.id))[0].sent_by_email
    sender.send.side_effect = None
    await service._send_email(notification, user.email.value)
    assert (await repository.list_for_user(user.id))[0].sent_by_email
    assert "&lt;dato&gt;" in sender.send.call_args.args[2]
    await service._send_email(notification, user.email.value)
    assert sender.send.await_count == 2


def test_no_invented_indicator_formula_and_valid_signatory_data():
    indicator = PoaFormIndicator.create(form_id=1, indicator_key="6.1.2", target_value=Decimal(100))
    with pytest.raises(ValidationError):
        indicator.capture_total(total_achieved=Decimal(20), achieved_percentage=None)
    indicator.capture_total(total_achieved=Decimal(20), achieved_percentage=Decimal(5))
    assert indicator.achieved_percentage == Decimal(5)
    with pytest.raises(ValidationError):
        PoaSignatory(name="  ", position="Rectoría")
