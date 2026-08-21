"""Entidad Captura y reglas de edicion/envio."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.shared.domain.base_entity import BaseEntity
from app.shared.domain.exceptions import CaptureImmutableError, InvalidStateError, ValidationError

from .value_objects import CaptureStatus


@dataclass(kw_only=True)
class Capture(BaseEntity):
    indicator_id: int
    period_id: int
    capturer_id: int
    result: Decimal | None = None
    source_data: str | None = None
    activity: str | None = None
    observations: str | None = None
    status: CaptureStatus = CaptureStatus.DRAFT
    progress_percentage: Decimal | None = None
    semaphore: str | None = None

    @classmethod
    def create(cls, *, indicator_id: int, period_id: int, capturer_id: int, **values) -> Capture:
        return cls(
            indicator_id=indicator_id,
            period_id=period_id,
            capturer_id=capturer_id,
            result=values.get("result"),
            source_data=values.get("source_data"),
            activity=values.get("activity"),
            observations=values.get("observations"),
        )

    def ensure_editable(self, period_is_open: bool) -> None:
        if self.status is CaptureStatus.VALIDATED:
            raise CaptureImmutableError()
        if self.status is CaptureStatus.SENT:
            raise InvalidStateError("Una captura enviada no puede editarse.")

    def edit(self, *, period_is_open: bool, **changes) -> None:
        self.ensure_editable(period_is_open)
        for field_name, value in changes.items():
            if hasattr(self, field_name) and value is not None:
                setattr(self, field_name, value)
        self.touch()

    def send(self, *, has_evidence: bool, period_is_open: bool) -> None:
        if not period_is_open:
            raise InvalidStateError("No se puede enviar una captura con el periodo cerrado.")
        if self.status not in {CaptureStatus.DRAFT, CaptureStatus.REJECTED}:
            raise InvalidStateError("Solo una captura en borrador o rechazada puede enviarse.")
        if self.result is None:
            raise ValidationError("El resultado es obligatorio para enviar la captura.")
        if not has_evidence:
            raise ValidationError("La captura debe tener al menos una evidencia.")
        self.status = CaptureStatus.SENT
        self.touch()

    def validate(self) -> None:
        if self.status is not CaptureStatus.SENT:
            raise InvalidStateError("Solo una captura enviada puede validarse.")
        self.status = CaptureStatus.VALIDATED
        self.touch()

    def reject(self, comment: str) -> None:
        if self.status is not CaptureStatus.SENT:
            raise InvalidStateError("Solo una captura enviada puede rechazarse.")
        if not comment.strip():
            raise ValidationError("El comentario es obligatorio al rechazar una captura.")
        self.status = CaptureStatus.REJECTED
        self.observations = comment.strip()
        self.touch()
