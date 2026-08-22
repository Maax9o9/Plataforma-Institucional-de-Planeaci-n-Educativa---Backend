from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.modules.indicators_catalog.domain.entities import Indicator
from app.modules.indicators_catalog.domain.value_objects import IndicatorPeriodicity
from app.modules.indicators_catalog.infrastructure.repository import InMemoryIndicatorRepository
from app.modules.notifications.application.reminders import GenerateReminders
from app.modules.notifications.infrastructure.repository import InMemoryNotificationRepository
from app.modules.periods.domain.entities import Period
from app.modules.periods.domain.value_objects import Periodicity, PeriodType
from app.modules.periods.infrastructure.repository import InMemoryPeriodRepository
from app.modules.poa_planning.domain.entities import (
    PoaActivity,
    PoaExercise,
    PoaObjective,
    PoaProcess,
)
from app.modules.poa_planning.infrastructure.repository import InMemoryPoaRepository


@pytest.mark.asyncio
async def test_reminders_target_the_correct_indicator_and_poa_responsibles():
    today = date(2035, 1, 10)
    periods = InMemoryPeriodRepository()
    indicators = InMemoryIndicatorRepository()
    notifications = InMemoryNotificationRepository()
    poa = InMemoryPoaRepository()

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
    await poa.add_exercise(PoaExercise.create(today.year))
    exercise = next(iter(poa.exercises.values()))
    await poa.add_process(PoaProcess.create(exercise_id=exercise.id, name="Proceso", area_id=1))
    process = next(iter(poa.processes.values()))
    await poa.add_objective(
        PoaObjective.create(process_id=process.id, poa_indicator=None, objective="Objetivo")
    )
    objective = next(iter(poa.objectives.values()))
    await poa.add_activity(
        PoaActivity.create(
            objective_id=objective.id,
            description="Actividad",
            unit="Unidad",
            annual_goal=Decimal("10"),
            observations=None,
            responsible_id=202,
        )
    )

    use_case = GenerateReminders(periods, indicators, notifications, poa)
    assert await use_case.execute(today) == 2
    assert await use_case.execute(today) == 2  # segundo intento idempotente

    indicator_items = await notifications.list_for_user(101)
    poa_items = await notifications.list_for_user(202)
    assert len(indicator_items) == 1
    assert indicator_items[0].entity_id == indicator_period.id
    assert len(poa_items) == 1
    assert poa_items[0].entity_id == poa_period.id
