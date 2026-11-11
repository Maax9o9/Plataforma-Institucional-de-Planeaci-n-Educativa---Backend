"""Casos de uso separados para borrador, edicion y envio."""

from __future__ import annotations

from app.shared.application.event_bus import EventBus
from app.shared.domain.exceptions import ConflictError, ForbiddenError, ResourceNotFoundError

from ....evidence_management.domain.value_objects import FlowEntity
from ...domain.entities import Capture
from ...domain.events import CaptureCreated, CaptureSent, CaptureUpdated
from ...domain.ports.repositories import CaptureRepository, EvidenceReader, ReferenceReader
from ..dto import EditCaptureCommand, RegisterCaptureCommand, SendCaptureCommand


def _period_is_open(period) -> bool:
    return period is not None and period.status.value == "abierto"


class RegisterCapture:
    def __init__(
        self,
        repository: CaptureRepository,
        indicator_reader: ReferenceReader,
        period_reader: ReferenceReader,
        event_bus: EventBus,
    ) -> None:
        self.repository = repository
        self.indicator_reader = indicator_reader
        self.period_reader = period_reader
        self.event_bus = event_bus

    async def execute(self, command: RegisterCaptureCommand) -> Capture:
        indicator = await self.indicator_reader.get_by_id(command.indicator_id)
        if indicator is None or not indicator.is_active:
            raise ResourceNotFoundError("El indicador no existe o esta desactivado.")
        if indicator.responsible_id != command.capturer_id:
            raise ForbiddenError("El usuario no es el responsable del indicador.")
        period = await self.period_reader.get_by_id(command.period_id)
        if not _period_is_open(period):
            raise ConflictError("El periodo no existe o no esta abierto.")
        if getattr(period.period_type, "value", period.period_type) != "indicadores":
            raise ConflictError("Las capturas de indicadores requieren un periodo de indicadores.")
        if period.periodicity != indicator.periodicity:
            raise ConflictError("La periodicidad del periodo no coincide con el indicador.")
        existing = await self.repository.get_by_indicator_period(
            command.indicator_id,
            command.period_id,
        )
        if existing is not None:
            raise ConflictError("Ya existe una captura para el indicador y periodo.")
        capture = Capture.create(
            indicator_id=command.indicator_id,
            period_id=command.period_id,
            capturer_id=command.capturer_id,
            result=command.result,
            source_data=command.source_data,
            activity=command.activity,
            observations=command.observations,
        )
        await self.repository.add(capture)
        await self.event_bus.publish(
            CaptureCreated(
                actor_id=command.capturer_id,
                aggregate_type="capture",
                aggregate_id=capture.id,
                action="created",
                data={"indicator_id": capture.indicator_id, "period_id": capture.period_id},
            )
        )
        return capture


class EditCapture:
    def __init__(
        self,
        repository: CaptureRepository,
        period_reader: ReferenceReader,
        event_bus: EventBus,
    ) -> None:
        self.repository = repository
        self.period_reader = period_reader
        self.event_bus = event_bus

    async def execute(self, command: EditCaptureCommand) -> Capture:
        capture = await self.repository.get_by_id(command.capture_id)
        if capture is None:
            raise ResourceNotFoundError("La captura no existe.")
        if capture.capturer_id != command.actor_id:
            raise ForbiddenError("El usuario no es el capturista de la captura.")
        if command.expected_version is not None and command.expected_version != capture.version:
            raise ConflictError(
                "La captura fue modificada por otra solicitud.",
                details={"version_actual": capture.version},
            )
        period = await self.period_reader.get_by_id(capture.period_id)
        capture.edit(
            period_is_open=_period_is_open(period),
            result=command.result,
            source_data=command.source_data,
            activity=command.activity,
            observations=command.observations,
        )
        await self.repository.update(capture)
        await self.event_bus.publish(
            CaptureUpdated(
                actor_id=command.actor_id,
                aggregate_type="capture",
                aggregate_id=capture.id,
                action="updated",
                data={"indicator_id": capture.indicator_id},
            )
        )
        return capture


class SendCapture:
    def __init__(
        self,
        repository: CaptureRepository,
        period_reader: ReferenceReader,
        evidence_reader: EvidenceReader,
        event_bus: EventBus,
    ) -> None:
        self.repository = repository
        self.period_reader = period_reader
        self.evidence_reader = evidence_reader
        self.event_bus = event_bus

    async def execute(self, command: SendCaptureCommand) -> Capture:
        capture = await self.repository.get_by_id(command.capture_id)
        if capture is None:
            raise ResourceNotFoundError("La captura no existe.")
        if capture.capturer_id != command.actor_id:
            raise ForbiddenError("El usuario no es el capturista de la captura.")
        period = await self.period_reader.get_by_id(capture.period_id)
        has_evidence = await self.evidence_reader.has_for(FlowEntity.CAPTURE, capture.id)
        previous_status = capture.status
        capture.send(has_evidence=has_evidence, period_is_open=_period_is_open(period))
        await self.repository.update(capture)
        await self.event_bus.publish(
            CaptureSent(
                actor_id=command.actor_id,
                aggregate_type="capture",
                aggregate_id=capture.id,
                action="sent",
                data={
                    "indicator_id": capture.indicator_id,
                    "period_id": capture.period_id,
                    "from_status": previous_status.value,
                },
            )
        )
        return capture
