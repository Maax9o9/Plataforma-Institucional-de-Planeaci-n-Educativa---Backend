from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.identity_access.domain.entities import User
from app.modules.identity_access.domain.value_objects import Role
from app.modules.indicators_catalog.domain.entities import Indicator
from app.modules.indicators_catalog.domain.value_objects import IndicatorPeriodicity
from app.modules.indicators_catalog.infrastructure.repository import InMemoryIndicatorRepository
from app.modules.notifications.application.reminders import GenerateReminders
from app.modules.notifications.infrastructure.repository import InMemoryNotificationRepository
from app.modules.periods.domain.entities import Period
from app.modules.periods.domain.value_objects import Periodicity, PeriodType
from app.modules.periods.infrastructure.repository import InMemoryPeriodRepository
from app.modules.poa_planning.application.period_recipients import (
    PoaPendingCapture,
    PoaPeriodRecipients,
)


@pytest.mark.asyncio
async def test_reminders_target_the_correct_indicator_and_poa_responsibles():
    today = date(2035, 1, 10)
    periods = InMemoryPeriodRepository()
    indicators = InMemoryIndicatorRepository()
    notifications = InMemoryNotificationRepository()
    indicator_period = Period.create(
        name="Indicadores mensual",
        starts_on=today - timedelta(days=20),
        ends_on=today + timedelta(days=5),
        period_type=PeriodType.INDICATORS,
        periodicity=Periodicity.MONTHLY,
        year=today.year,
    )
    indicator_period.open()
    await periods.add(indicator_period)
    poa_period = Period.create(
        name="POA cuatrimestre",
        starts_on=today - timedelta(days=20),
        ends_on=today + timedelta(days=5),
        period_type=PeriodType.POA,
        periodicity=None,
        year=today.year,
    )
    poa_period.open()
    await periods.add(poa_period)
    await indicators.add(
        Indicator.create(
            key="REM-01",
            name="Indicador con recordatorio",
            calculation_method="Resultado / meta",
            unit="Porcentaje",
            area_id=1,
            responsible_id=101,
            periodicity=IndicatorPeriodicity.MONTHLY,
        )
    )
    recipients = AsyncMock()
    recipients.pending_for_period.return_value = [
        PoaPendingCapture("poa_form_activity", 1, frozenset({202}), "Pendiente")
    ]
    use_case = GenerateReminders(periods, indicators, notifications, recipients)
    assert await use_case.execute(today) == 2
    assert await use_case.execute(today) == 2
    recipients.pending_for_period.assert_awaited_with(poa_period.id)
    assert len(await notifications.list_for_user(101)) == 1
    assert len(await notifications.list_for_user(202)) == 1


@pytest.mark.asyncio
async def test_current_poa_recipients_require_exact_period_area_and_role():
    forms = AsyncMock()
    forms.list_forms.return_value = [SimpleNamespace(id=1)]
    forms.list_form_quarters.return_value = [SimpleNamespace(period_id=41)]
    forms.get_detail.return_value = SimpleNamespace(
        activities=[SimpleNamespace(executing_area_id=2), SimpleNamespace(executing_area_id=None)]
    )
    users = AsyncMock()
    accounts = []
    for index, (role, area) in enumerate(
        (
            (Role.CAPTURISTA_POA, 2),
            (Role.CAPTURISTA_POA, 3),
            (Role.CAPTURISTA_POA, None),
            (Role.REVISOR_POA, 2),
            (Role.ADMIN_SISTEMA, None),
        ),
        start=1,
    ):
        user = User.register(
            email=f"u{index}@example.com",
            full_name="Usuario",
            password_hash="not-used",
            roles={role},
            area_id=area,
        )
        user.id = index
        accounts.append(user)
    users.list.return_value = accounts
    policy = PoaPeriodRecipients(forms, users)
    assert await policy.for_period(41) == {1, 5}
    assert await policy.for_period(42) == set()
    users.list.assert_awaited_with(active_only=True)
