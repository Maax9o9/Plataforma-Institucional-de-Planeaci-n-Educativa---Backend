"""Entidades de la cédula institucional del Programa Operativo Anual."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.modules.indicators_capture.domain.value_objects import CaptureStatus
from app.shared.domain.base_entity import BaseEntity, utc_now
from app.shared.domain.exceptions import InvalidStateError, ValidationError

FOUR_MONTH_LABELS = {
    1: "Enero-Abril",
    2: "Mayo-Agosto",
    3: "Septiembre-Diciembre",
}

STRATEGY_TYPES = ("Eficiencia", "Eficacia", "Pertinencia", "Vinculación", "Equidad de Género")


@dataclass(frozen=True, kw_only=True)
class PoaSignatory:
    name: str
    position: str

    def __post_init__(self) -> None:
        for attribute in ("name", "position"):
            value = getattr(self, attribute).strip()
            if not value or len(value) > 200:
                raise ValidationError(
                    "Cada firmante requiere nombre y cargo de hasta 200 caracteres."
                )
            object.__setattr__(self, attribute, value)


def validate_presentation(strategy_type: str | None, signatories: tuple[PoaSignatory, ...]) -> None:
    if strategy_type is not None and strategy_type not in STRATEGY_TYPES:
        raise ValidationError("El tipo de estrategia no pertenece al catálogo POA.")
    if len(signatories) not in {0, 2}:
        raise ValidationError("El bloque de firmas requiere exactamente dos firmantes.")


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
    strategy_type: str | None = None
    signatories: tuple[PoaSignatory, ...] = ()
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
        strategy_type: str | None = None,
        signatories: tuple[PoaSignatory, ...] = (),
    ) -> PoaForm:
        validate_presentation(strategy_type, signatories)
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
            strategy_type=strategy_type,
            signatories=signatories,
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
        strategy_type: str | None = None,
        signatories: tuple[PoaSignatory, ...] | None = None,
    ) -> None:
        validate_presentation(strategy_type, signatories if signatories is not None else ())
        if strategy_type is not None:
            self.strategy_type = strategy_type
        if signatories is not None:
            self.signatories = signatories
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
        # El denominador depende de la fórmula del catálogo, no de la meta a lograr.
        if achieved_percentage is None:
            raise ValidationError("Indique el porcentaje alcanzado según la fórmula del indicador.")
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
    #: Explicacion concreta de la actividad para el area que la ejecuta: el
    #: texto oficial del POA federal es generico, y Planeacion le agrega aqui
    #: que significa en los hechos ("actividad UPE Chiapas").
    upe_description: str | None = None
    #: Los criterios SEAES son siete y son indicativos: una actividad puede
    #: caer en varios a la vez, por eso es un conjunto y no un valor unico.
    criteria_seaes_ids: tuple[int, ...] = ()

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
        upe_description: str | None = None,
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
        if upe_description is not None:
            self.upe_description = upe_description.strip() or None
        self.touch()

    def assign_criteria(self, criteria_seaes_ids: Iterable[int]) -> None:
        """Reemplaza el conjunto completo de criterios SEAES de la actividad.

        Antes había un único criterio; ahora SEAES define siete criterios
        indicativos y una actividad puede caer en varios a la vez. El método
        reemplaza el conjunto entero en vez de acumularlo, porque una lista
        vacía es la forma legítima de retirarlos todos —igual que antes
        `None` desasignaba el criterio único—, y eso no se puede expresar si
        `[]` significara "no tocar nada".
        """
        self.criteria_seaes_ids = tuple(sorted(set(criteria_seaes_ids)))
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
    #: Mismo ciclo que la captura de indicadores, para que el area y Planeacion
    #: no tengan que aprender dos flujos distintos.
    status: CaptureStatus = CaptureStatus.DRAFT
    review_comment: str | None = None

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

    def ensure_editable(self) -> None:
        """Un seguimiento enviado o validado deja de ser del area (HU-08.01, HU-08.04)."""
        if self.status is CaptureStatus.VALIDATED:
            raise InvalidStateError(
                "Un seguimiento validado no puede modificarse; requiere reapertura formal."
            )
        if self.status is CaptureStatus.SENT:
            raise InvalidStateError("Un seguimiento enviado a revisión no puede editarse.")

    def send(self, *, has_evidence: bool) -> None:
        """HU-08.01: el area lo manda a revision."""
        if self.status not in {CaptureStatus.DRAFT, CaptureStatus.REJECTED}:
            raise InvalidStateError(
                "Sólo un seguimiento en borrador o rechazado puede enviarse a revisión."
            )
        if self.achieved is None:
            raise ValidationError("El valor alcanzado es obligatorio para enviar a revisión.")
        if not (self.progress or "").strip():
            raise ValidationError("El progreso es obligatorio para enviar a revisión.")
        if not has_evidence:
            raise ValidationError("El seguimiento debe tener al menos una evidencia.")
        self.status = CaptureStatus.SENT
        self.review_comment = None
        self.touch()

    def validate(self) -> None:
        """HU-08.02: Planeacion lo aprueba."""
        if self.status is not CaptureStatus.SENT:
            raise InvalidStateError("Sólo un seguimiento enviado puede validarse.")
        self.status = CaptureStatus.VALIDATED
        self.review_comment = None
        self.touch()

    def reject(self, comment: str) -> None:
        """HU-08.02 y HU-08.03: vuelve al area con el motivo visible."""
        if self.status is not CaptureStatus.SENT:
            raise InvalidStateError("Sólo un seguimiento enviado puede rechazarse.")
        normalized = comment.strip()
        if not normalized:
            raise ValidationError("El comentario es obligatorio al rechazar un seguimiento.")
        self.status = CaptureStatus.REJECTED
        self.review_comment = normalized
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


@dataclass
class PoaFollowUpCard:
    """Una tarjeta del tablero: el seguimiento con lo que hace falta para decidir
    sin abrirlo. Es un modelo de lectura, no un agregado: no tiene reglas."""

    id: int
    form_id: int
    activity_id: int
    activity_key: str
    unit: str
    annual_goal: Decimal
    executing_area_id: int | None
    criteria_seaes_ids: tuple[int, ...]
    quarter: int
    period_id: int
    scheduled: Decimal
    achieved: Decimal | None
    status: CaptureStatus
    review_comment: str | None
    # Lo que el area escribio, no solo lo que midio. Viaja en la tarjeta porque
    # el formulario de captura se abre desde ahi y el PUT que lo guarda
    # reemplaza el seguimiento entero: sin estos campos el formulario abriria
    # en blanco y la siguiente correccion borraria el texto.
    deviation_justification: str | None
    progress: str | None
    scope: str | None
    updated_at: datetime
