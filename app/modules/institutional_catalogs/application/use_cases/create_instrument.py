"""Alta de instrumentos institucionales."""

from app.shared.application.event_bus import EventBus
from app.shared.domain.exceptions import ConflictError, ValidationError

from ...domain.entities import Instrument
from ...domain.events import InstrumentCreated
from ...domain.ports.repositories import InstrumentRepository
from ..dto import CreateInstrumentCommand


class CreateInstrument:
    def __init__(self, repository: InstrumentRepository, event_bus: EventBus) -> None:
        self.repository = repository
        self.event_bus = event_bus

    async def execute(self, command: CreateInstrumentCommand) -> Instrument:
        if command.code.strip().upper() != "PIDE":
            raise ValidationError("El unico instrumento habilitado actualmente es PIDE.")
        existing_codes = {
            instrument.code for instrument in await self.repository.list(active_only=False)
        }
        if command.code.strip().upper() in existing_codes:
            raise ConflictError("Ya existe un instrumento con ese codigo.")
        instrument = Instrument.create(
            code=command.code,
            name=command.name,
            description=command.description,
        )
        await self.repository.add(instrument)
        await self.event_bus.publish(
            InstrumentCreated(
                actor_id=command.actor_id,
                aggregate_type="instrument",
                aggregate_id=instrument.id,
                action="created",
                data={"code": instrument.code, "name": instrument.name},
            )
        )
        return instrument
