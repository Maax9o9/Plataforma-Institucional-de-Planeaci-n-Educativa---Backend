"""Entidades de la cédula institucional del Programa Operativo Anual."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.shared.domain.base_entity import BaseEntity, utc_now
from app.shared.domain.exceptions import ValidationError

FOUR_MONTH_LABELS = {
    1: "Enero-Abril",
    2: "Mayo-Agosto",
    3: "Septiembre-Diciembre",
}


def _require_non_negative(value: Decimal | None, label: str) -> None:
    if value is not None and value < 0:
        raise ValidationError(f"{label} no puede ser negativo.")


def _require_percentage(value: Decimal | None, label: str) -> None:
    if value is not None and not Decimal(0) <= value <= Decimal(100):
        raise ValidationError(f"{label} debe estar entre 0 y 100.")


def four_month_period_name(quarter: int) -> str:
    try:
        return FOUR_MONTH_LABELS[quarter]
    except KeyError as exc:
        raise ValidationError("El cuatrimestre debe ser 1, 2 o 3.") from exc


def build_issue_name(objective_number: int, quarter: int, year: int) -> str:
    return f"Cédula Objetivo {objective_number} - {four_month_period_name(quarter)} {year}"


@dataclass(frozen=True, kw_only=True)
class PoaObjectiveCatalog:
    key: str
    number: int
    denomination: str
    is_active: bool = True


@dataclass(frozen=True, kw_only=True)
class PoaStrategyCatalog:
    key: str
    objective_number: int
    denomination: str
    is_active: bool = True


@dataclass(frozen=True, kw_only=True)
class PoaIndicatorCatalog:
    key: str
    objective_number: int
    name: str
    formula: str
    unit: str
    is_active: bool = True


@dataclass(frozen=True, kw_only=True)
class PoaActivityCatalog:
    key: str
    strategy_key: str
    description: str
    is_active: bool = True


@dataclass(kw_only=True)
class PoaForm(BaseEntity):
    exercise_id: int
    objective_number: int
    strategy_key: str
    responsible_area_id: int
    created_by: int
    scope_and_socioeconomic_effect: str | None = None
    version: int = 1

    @classmethod
    def create(
        cls,
        *,
        exercise_id: int,
        objective_number: int,
        strategy_key: str,
        responsible_area_id: int,
        created_by: int,
        scope_and_socioeconomic_effect: str | None = None,
    ) -> PoaForm:
        if objective_number not in range(1, 7):
            raise ValidationError("El objetivo del POA debe estar entre 1 y 6.")
        if not strategy_key.strip():
            raise ValidationError("La estrategia de la cédula es obligatoria.")
        return cls(
            exercise_id=exercise_id,
            objective_number=objective_number,
            strategy_key=strategy_key.strip(),
            responsible_area_id=responsible_area_id,
            created_by=created_by,
            scope_and_socioeconomic_effect=(
                scope_and_socioeconomic_effect.strip() if scope_and_socioeconomic_effect else None
            ),
        )

    def update_details(
        self,
        *,
        objective_number: int | None = None,
        strategy_key: str | None = None,
        responsible_area_id: int | None = None,
        scope_and_socioeconomic_effect: str | None = None,
    ) -> None:
        if objective_number is not None:
            if objective_number not in range(1, 7):
                raise ValidationError("El objetivo del POA debe estar entre 1 y 6.")
            self.objective_number = objective_number
        if strategy_key is not None:
            if not strategy_key.strip():
                raise ValidationError("La estrategia de la cédula es obligatoria.")
            self.strategy_key = strategy_key.strip()
        if responsible_area_id is not None:
            self.responsible_area_id = responsible_area_id
        if scope_and_socioeconomic_effect is not None:
            normalized = scope_and_socioeconomic_effect.strip()
            self.scope_and_socioeconomic_effect = normalized or None
        self.touch()


@dataclass(kw_only=True)
class PoaFormQuarter(BaseEntity):
    form_id: int
    quarter: int
    period_id: int
    starts_on: date
    ends_on: date

    @classmethod
    def create(
        cls,
        *,
        form_id: int,
        quarter: int,
        period_id: int,
        starts_on: date,
        ends_on: date,
    ) -> PoaFormQuarter:
        four_month_period_name(quarter)
        if ends_on <= starts_on:
            raise ValidationError("La fecha final debe ser posterior a la fecha inicial.")
        return cls(
            form_id=form_id,
            quarter=quarter,
            period_id=period_id,
            starts_on=starts_on,
            ends_on=ends_on,
        )


@dataclass(kw_only=True)
class PoaFormIndicator(BaseEntity):
    form_id: int
    indicator_key: str
    institutional_goal: Decimal | None = None
    baseline_year: int | None = None
    baseline_value: Decimal | None = None
    current_percentage: Decimal | None = None
    target_value: Decimal | None = None
    target_percentage: Decimal | None = None
    total_achieved: Decimal | None = None
    achieved_percentage: Decimal | None = None

    @classmethod
    def create(cls, *, form_id: int, indicator_key: str, **values) -> PoaFormIndicator:
        for field_name, label in (
            ("institutional_goal", "La meta institucional"),
            ("baseline_value", "La línea base"),
            ("target_value", "El número a lograr"),
        ):
            _require_non_negative(values.get(field_name), label)
        for field_name, label in (
            ("current_percentage", "El porcentaje actual"),
            ("target_percentage", "El porcentaje a lograr"),
        ):
            _require_percentage(values.get(field_name), label)
        baseline_year = values.get("baseline_year")
        if baseline_year is not None and not 2000 <= baseline_year <= 2200:
            raise ValidationError("El año de la línea base no es válido.")
        return cls(form_id=form_id, indicator_key=indicator_key, **values)

    def update_details(self, **values) -> None:
        for field_name, label in (
            ("institutional_goal", "La meta institucional"),
            ("baseline_value", "La línea base"),
            ("target_value", "El número a lograr"),
        ):
            if field_name in values:
                _require_non_negative(values[field_name], label)
        for field_name, label in (
            ("current_percentage", "El porcentaje actual"),
            ("target_percentage", "El porcentaje a lograr"),
        ):
            if field_name in values:
                _require_percentage(values[field_name], label)
        baseline_year = values.get("baseline_year")
        if baseline_year is not None and not 2000 <= baseline_year <= 2200:
            raise ValidationError("El año de la línea base no es válido.")
        for field_name, value in values.items():
            setattr(self, field_name, value)
        self.touch()

    def capture_total(
        self, *, total_achieved: Decimal, achieved_percentage: Decimal | None
    ) -> None:
        _require_non_negative(total_achieved, "El total alcanzado")
        if achieved_percentage is None and self.target_value not in {None, Decimal(0)}:
            achieved_percentage = total_achieved / self.target_value * Decimal(100)
        _require_non_negative(achieved_percentage, "El porcentaje alcanzado")
        self.total_achieved = total_achieved
        self.achieved_percentage = achieved_percentage
        self.touch()


@dataclass(kw_only=True)
class PoaFormActivity(BaseEntity):
    form_id: int
    activity_key: str
    unit: str
    annual_goal: Decimal
    executing_area_id: int | None = None
    observations: str | None = None

    @classmethod
    def create(
        cls,
        *,
        form_id: int,
        activity_key: str,
        unit: str,
        annual_goal: Decimal,
        executing_area_id: int | None = None,
        observations: str | None = None,
    ) -> PoaFormActivity:
        if not unit.strip():
            raise ValidationError("La unidad de medida de la actividad es obligatoria.")
        _require_non_negative(annual_goal, "La meta anual")
        return cls(
            form_id=form_id,
            activity_key=activity_key,
            unit=unit.strip(),
            annual_goal=annual_goal,
            executing_area_id=executing_area_id,
            observations=observations.strip() if observations else None,
        )

    def update_details(
        self,
        *,
        unit: str | None = None,
        annual_goal: Decimal | None = None,
        executing_area_id: int | None = None,
        observations: str | None = None,
    ) -> None:
        if unit is not None:
            if not unit.strip():
                raise ValidationError("La unidad de medida de la actividad es obligatoria.")
            self.unit = unit.strip()
        if annual_goal is not None:
            _require_non_negative(annual_goal, "La meta anual")
            self.annual_goal = annual_goal
        if executing_area_id is not None:
            self.executing_area_id = executing_area_id
        if observations is not None:
            self.observations = observations.strip() or None
        self.touch()


@dataclass(kw_only=True)
class PoaActivityFollowUp(BaseEntity):
    form_activity_id: int
    quarter: int
    period_id: int
    captured_by: int
    scheduled: Decimal
    achieved: Decimal | None = None
    deviation_justification: str | None = None
    progress: str | None = None
    scope: str | None = None

    @classmethod
    def create(
        cls,
        *,
        form_activity_id: int,
        quarter: int,
        period_id: int,
        captured_by: int,
        scheduled: Decimal,
        achieved: Decimal | None = None,
        deviation_justification: str | None = None,
        progress: str | None = None,
        scope: str | None = None,
    ) -> PoaActivityFollowUp:
        four_month_period_name(quarter)
        _require_non_negative(scheduled, "El valor programado")
        _require_non_negative(achieved, "El valor alcanzado")
        return cls(
            form_activity_id=form_activity_id,
            quarter=quarter,
            period_id=period_id,
            captured_by=captured_by,
            scheduled=scheduled,
            achieved=achieved,
            deviation_justification=(
                deviation_justification.strip() if deviation_justification else None
            ),
            progress=progress.strip() if progress else None,
            scope=scope.strip() if scope else None,
        )

    def update_justification(self, justification: str) -> None:
        normalized = justification.strip()
        if not normalized:
            raise ValidationError("La justificación de desviaciones es obligatoria.")
        self.deviation_justification = normalized
        self.touch()


@dataclass(kw_only=True)
class PoaFormDetail:
    form: PoaForm
    quarters: list[PoaFormQuarter] = field(default_factory=list)
    indicators: list[PoaFormIndicator] = field(default_factory=list)
    activities: list[PoaFormActivity] = field(default_factory=list)
    follow_ups: list[PoaActivityFollowUp] = field(default_factory=list)


@dataclass(kw_only=True)
class PoaFormIssue(BaseEntity):
    form_id: int
    quarter: int
    period_id: int
    name: str
    snapshot: dict[str, Any]
    issued_by: int
    issued_at: datetime = field(default_factory=utc_now)
