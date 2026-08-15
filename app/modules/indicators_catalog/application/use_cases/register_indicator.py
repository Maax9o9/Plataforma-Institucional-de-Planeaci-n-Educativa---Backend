"""Registrar un indicador completo y clasificado."""

from __future__ import annotations

from app.shared.application.event_bus import EventBus
from app.shared.domain.exceptions import ConflictError, ValidationError

from ...domain.entities import Indicator
from ...domain.events import IndicatorCreated
from ...domain.ports.repositories import IndicatorRepository, ReferenceReader
from ..dto import RegisterIndicatorCommand


class RegisterIndicator:
    def __init__(
        self,
        repository: IndicatorRepository,
        area_reader: ReferenceReader,
        user_reader: ReferenceReader,
        instrument_reader: ReferenceReader,
        indicator_type_reader: ReferenceReader,
        event_bus: EventBus,
    ) -> None:
        self.repository = repository
        self.area_reader = area_reader
        self.user_reader = user_reader
        self.instrument_reader = instrument_reader
        self.indicator_type_reader = indicator_type_reader
        self.event_bus = event_bus

    async def execute(self, command: RegisterIndicatorCommand) -> Indicator:
        if await self.repository.get_by_key(command.key):
            raise ConflictError("Ya existe un indicador con esa clave.")
        area = await self.area_reader.get_by_id(command.area_id)
        if area is None or not area.is_active:
            raise ValidationError("El area no existe o esta desactivada.")
        user = await self.user_reader.get_by_id(command.responsible_id)
        if user is None or not user.is_active:
            raise ValidationError("El responsable no existe o esta desactivado.")
        for instrument_id in command.instrument_ids:
            instrument = await self.instrument_reader.get_by_id(instrument_id)
            if instrument is None or not instrument.is_active:
                raise ValidationError(
                    f"El instrumento {instrument_id} no existe o esta desactivado."
                )
        if command.indicator_type_id is not None:
            indicator_type = await self.indicator_type_reader.get_by_id(command.indicator_type_id)
            if indicator_type is None:
                raise ValidationError("El tipo de indicador no existe.")

        indicator = Indicator.create(
            key=command.key,
            name=command.name,
            calculation_method=command.calculation_method,
            unit=command.unit,
            area_id=command.area_id,
            responsible_id=command.responsible_id,
            periodicity=command.periodicity,
            definition=command.definition,
            dimension=command.dimension,
            verification_document=command.verification_document,
            information_source=command.information_source,
            methodological_notes=command.methodological_notes,
            indicator_type_id=command.indicator_type_id,
            instrument_ids=command.instrument_ids,
            green_threshold=command.green_threshold,
            yellow_threshold=command.yellow_threshold,
        )
        await self.repository.add(indicator)
        await self.event_bus.publish(
            IndicatorCreated(
                actor_id=command.actor_id,
                aggregate_type="indicator",
                aggregate_id=indicator.id,
                action="created",
                data={"key": indicator.key, "name": indicator.name},
            )
        )
        return indicator
