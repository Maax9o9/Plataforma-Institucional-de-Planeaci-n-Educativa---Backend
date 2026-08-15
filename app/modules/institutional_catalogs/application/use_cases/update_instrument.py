"""Editar y desactivar instrumentos sin DELETE."""

from __future__ import annotations

from app.shared.application.event_bus import EventBus
from app.shared.domain.exceptions import ResourceNotFoundError, ValidationError

from ...domain.entities import Instrument
from ...domain.events import InstrumentDeactivated, InstrumentUpdated
from ...domain.ports.repositories import InstrumentRepository
from ..dto import ChangeCatalogStatusCommand, UpdateInstrumentCommand


class UpdateInstrument:
    def __init__(self, repository: InstrumentRepository, event_bus: EventBus) -> None:
        self.repository = repository
        self.event_bus = event_bus

    async def execute(self, command: UpdateInstrumentCommand) -> Instrument:
        if command.code is not None and command.code.strip().upper() != "PIDE":
            raise ValidationError("El unico instrumento habilitado actualmente es PIDE.")
        instrument = await self.repository.get_by_id(command.instrument_id)
        if instrument is None:
            raise ResourceNotFoundError("El instrumento no existe.")
        instrument.update_details(
            code=command.code,
            name=command.name,
            description=command.description,
        )
        await self.repository.update(instrument)
        await self.event_bus.publish(
            InstrumentUpdated(
                actor_id=command.actor_id,
                aggregate_type="instrument",
                aggregate_id=instrument.id,
                action="updated",
                data={"code": instrument.code, "name": instrument.name},
            )
        )
        return instrument


class DeactivateInstrument:
    def __init__(self, repository: InstrumentRepository, event_bus: EventBus) -> None:
        self.repository = repository
        self.event_bus = event_bus

    async def execute(self, command: ChangeCatalogStatusCommand) -> Instrument:
        instrument = await self.repository.get_by_id(command.item_id)
        if instrument is None:
            raise ResourceNotFoundError("El instrumento no existe.")
        instrument.deactivate()
        await self.repository.update(instrument)
        await self.event_bus.publish(
            InstrumentDeactivated(
                actor_id=command.actor_id,
                aggregate_type="instrument",
                aggregate_id=instrument.id,
                action="deactivated",
                data={"code": instrument.code},
            )
        )
        return instrument
