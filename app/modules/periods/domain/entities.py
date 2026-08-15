"""Entidad Period con sus transiciones de negocio."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.shared.domain.base_entity import BaseEntity
from app.shared.domain.exceptions import InvalidStateError, ValidationError

from .value_objects import Periodicity, PeriodStatus, PeriodType


@dataclass(kw_only=True)
class Period(BaseEntity):
    name: str
    starts_on: date
    ends_on: date
    period_type: PeriodType = PeriodType.INDICATORS
    periodicity: Periodicity | None = Periodicity.MONTHLY
    year: int = 0
    status: PeriodStatus = PeriodStatus.DRAFT
    reopen_reason: str | None = None
    reopened_by: int | None = None

    @classmethod
    def create(
        cls,
        *,
        name: str,
        starts_on: date,
        ends_on: date,
        period_type: PeriodType = PeriodType.INDICATORS,
        periodicity: Periodicity | None = Periodicity.MONTHLY,
        year: int | None = None,
    ) -> Period:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValidationError("El nombre del periodo es obligatorio.")
        if ends_on <= starts_on:
            raise ValidationError("La fecha final debe ser posterior a la fecha inicial.")
        if period_type is PeriodType.INDICATORS and periodicity is None:
            raise ValidationError("La periodicidad es obligatoria para periodos de indicadores.")
        if period_type is PeriodType.POA and periodicity is not None:
            raise ValidationError("Un periodo POA no debe tener periodicidad.")
        resolved_year = year or starts_on.year
        if not 2000 <= resolved_year <= 2200:
            raise ValidationError("El anio del periodo no es valido.")
        return cls(
            name=normalized_name,
            starts_on=starts_on,
            ends_on=ends_on,
            period_type=period_type,
            periodicity=periodicity,
            year=resolved_year,
        )

    def open(self) -> None:
        if self.status is not PeriodStatus.DRAFT:
            raise InvalidStateError("Solo un periodo en borrador puede abrirse.")
        self.status = PeriodStatus.OPEN
        self.touch()

    def close(self) -> None:
        if self.status is not PeriodStatus.OPEN:
            raise InvalidStateError("Solo un periodo abierto puede cerrarse.")
        self.status = PeriodStatus.CLOSED
        self.touch()

    def reopen(self, reason: str, actor_id: int | None = None) -> None:
        normalized_reason = reason.strip()
        if self.status is not PeriodStatus.CLOSED:
            raise InvalidStateError("Solo un periodo cerrado puede reabrirse.")
        if not normalized_reason:
            raise ValidationError("El motivo de reapertura es obligatorio.")
        self.status = PeriodStatus.OPEN
        self.reopen_reason = normalized_reason
        self.reopened_by = actor_id
        self.touch()
