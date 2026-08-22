"""Entidad de avance cuatrimestral del POA."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.shared.domain.base_entity import BaseEntity
from app.shared.domain.exceptions import CaptureImmutableError, InvalidStateError, ValidationError

from ...indicators_capture.domain.value_objects import CaptureStatus


@dataclass(kw_only=True)
class PoaAdvance(BaseEntity):
    activity_id: int
    quarter: int
    period_id: int
    capturer_id: int
    scheduled: Decimal | None = None
    achieved: Decimal | None = None
    observations: str | None = None
    compliance_percentage: Decimal | None = None
    status: CaptureStatus = CaptureStatus.DRAFT
    criteria_ids: set[int] = field(default_factory=set)
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def create(
        cls, *, activity_id: int, quarter: int, period_id: int, capturer_id: int, **values
    ) -> PoaAdvance:
        if quarter not in {1, 2, 3}:
            raise ValidationError("El cuatrimestre debe ser 1, 2 o 3.")
        return cls(
            activity_id=activity_id,
            quarter=quarter,
            period_id=period_id,
            capturer_id=capturer_id,
            scheduled=values.get("scheduled"),
            achieved=values.get("achieved"),
            observations=values.get("observations"),
            criteria_ids=set(values.get("criteria_ids", set())),
        )

    def ensure_editable(self, *, period_is_open: bool) -> None:
        if self.status is CaptureStatus.VALIDATED:
            raise CaptureImmutableError("El avance POA validado no admite modificaciones.")
        if self.status is CaptureStatus.SENT:
            raise InvalidStateError("Un avance enviado no puede editarse.")
        if not period_is_open:
            raise InvalidStateError("El periodo POA no esta abierto.")

    def edit(self, *, period_is_open: bool, **changes) -> None:
        self.ensure_editable(period_is_open=period_is_open)
        for name, value in changes.items():
            if value is not None and hasattr(self, name):
                setattr(self, name, value)
        self.touch()

    def send(self, *, period_is_open: bool, has_evidence: bool) -> list[str]:
        if not period_is_open:
            raise InvalidStateError("El periodo POA no esta abierto.")
        if self.status not in {CaptureStatus.DRAFT, CaptureStatus.REJECTED}:
            raise InvalidStateError("Solo un avance en borrador o rechazado puede enviarse.")
        if self.scheduled is None or self.achieved is None:
            raise ValidationError("Programado y alcanzado son obligatorios para enviar.")
        if not self.observations or not self.observations.strip():
            raise ValidationError("Las observaciones son obligatorias para enviar.")
        if not self.criteria_ids:
            raise ValidationError("Debe asociarse al menos un criterio SEAES.")
        if self.scheduled == 0:
            raise ValidationError("El valor programado no puede ser cero.")
        if not has_evidence:
            raise ValidationError("El avance debe tener al menos una evidencia.")
        self.compliance_percentage = (self.achieved / self.scheduled) * Decimal(100)
        self.status = CaptureStatus.SENT
        self.touch()
        return []

    def validate(self) -> None:
        if self.status is not CaptureStatus.SENT:
            raise InvalidStateError("Solo un avance enviado puede validarse.")
        self.status = CaptureStatus.VALIDATED
        self.touch()

    def reject(self, comment: str) -> None:
        if self.status is not CaptureStatus.SENT:
            raise InvalidStateError("Solo un avance enviado puede rechazarse.")
        if not comment.strip():
            raise ValidationError("El comentario es obligatorio al rechazar un avance.")
        self.status = CaptureStatus.REJECTED
        self.observations = comment.strip()
        self.touch()
