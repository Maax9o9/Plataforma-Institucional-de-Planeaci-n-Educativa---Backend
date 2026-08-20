"""Entidades y reglas del catalogo maestro."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.shared.domain.base_entity import BaseEntity
from app.shared.domain.exceptions import ValidationError

from .value_objects import IndicatorPeriodicity


@dataclass(kw_only=True)
class Indicator(BaseEntity):
    key: str
    name: str
    calculation_method: str
    unit: str
    definition: str | None = None
    dimension: str | None = None
    verification_document: str | None = None
    information_source: str | None = None
    methodological_notes: str | None = None
    indicator_type_id: int | None = None
    area_id: int
    responsible_id: int
    periodicity: IndicatorPeriodicity = IndicatorPeriodicity.MONTHLY
    green_threshold: int | None = None
    yellow_threshold: int | None = None
    is_active: bool = True
    instrument_ids: set[int] = field(default_factory=set)
    criteria_ids: set[int] = field(default_factory=set)

    @classmethod
    def create(
        cls,
        *,
        key: str,
        name: str,
        calculation_method: str,
        unit: str,
        area_id: int,
        responsible_id: int,
        periodicity: IndicatorPeriodicity,
        definition: str | None = None,
        dimension: str | None = None,
        verification_document: str | None = None,
        information_source: str | None = None,
        methodological_notes: str | None = None,
        indicator_type_id: int | None = None,
        green_threshold: int | None = None,
        yellow_threshold: int | None = None,
        instrument_ids: set[int] | None = None,
    ) -> Indicator:
        values = {
            "key": key,
            "name": name,
            "calculation_method": calculation_method,
            "unit": unit,
        }
        for label, value in values.items():
            if not value or not value.strip():
                raise ValidationError(f"El campo {label} es obligatorio.")
        indicator = cls(
            key=key.strip().upper(),
            name=name.strip(),
            calculation_method=calculation_method.strip(),
            unit=unit.strip(),
            definition=definition,
            dimension=dimension,
            verification_document=verification_document,
            information_source=information_source,
            methodological_notes=methodological_notes,
            indicator_type_id=indicator_type_id,
            area_id=area_id,
            responsible_id=responsible_id,
            periodicity=periodicity,
            green_threshold=green_threshold,
            yellow_threshold=yellow_threshold,
            instrument_ids=set(instrument_ids or set()),
        )
        indicator.validate_thresholds()
        return indicator

    def validate_thresholds(self) -> None:
        if self.green_threshold is None and self.yellow_threshold is None:
            return
        if self.green_threshold is None or self.yellow_threshold is None:
            raise ValidationError("Los umbrales verde y amarillo deben configurarse juntos.")
        if not 0 <= self.yellow_threshold < self.green_threshold <= 100:
            raise ValidationError("Los umbrales deben cumplir 0 <= amarillo < verde <= 100.")

    def update(self, **changes) -> None:
        for field_name, value in changes.items():
            if value is not None and hasattr(self, field_name):
                if isinstance(value, str) and not value.strip():
                    raise ValidationError(f"El campo {field_name} no puede estar vacio.")
                setattr(self, field_name, value.strip() if isinstance(value, str) else value)
        self.validate_thresholds()
        self.touch()

    def set_periodicity(self, periodicity: IndicatorPeriodicity) -> None:
        self.periodicity = periodicity
        self.touch()

    def set_thresholds(self, green: int | None, yellow: int | None) -> None:
        self.green_threshold = green
        self.yellow_threshold = yellow
        self.validate_thresholds()
        self.touch()

    def deactivate(self) -> None:
        self.is_active = False
        self.touch()


@dataclass(frozen=True)
class Baseline:
    indicator_id: int
    year: int
    period: str | None
    value: Decimal


@dataclass(frozen=True)
class Goal:
    indicator_id: int
    period_id: int
    value: Decimal
