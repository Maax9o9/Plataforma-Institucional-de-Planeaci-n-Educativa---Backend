"""Composicion de casos de uso de catalogos."""

from fastapi import Request

from ..application.use_cases.create_area import CreateArea
from ..application.use_cases.create_instrument import CreateInstrument
from ..application.use_cases.update_area import DeactivateArea, UpdateArea
from ..application.use_cases.update_instrument import DeactivateInstrument, UpdateInstrument


def get_create_area_use_case(request: Request) -> CreateArea:
    return CreateArea(request.app.state.area_repository, request.app.state.event_bus)


def get_create_instrument_use_case(request: Request) -> CreateInstrument:
    return CreateInstrument(request.app.state.instrument_repository, request.app.state.event_bus)


def get_update_area_use_case(request: Request) -> UpdateArea:
    return UpdateArea(request.app.state.area_repository, request.app.state.event_bus)


def get_deactivate_area_use_case(request: Request) -> DeactivateArea:
    return DeactivateArea(request.app.state.area_repository, request.app.state.event_bus)


def get_update_instrument_use_case(request: Request) -> UpdateInstrument:
    return UpdateInstrument(request.app.state.instrument_repository, request.app.state.event_bus)


def get_deactivate_instrument_use_case(request: Request) -> DeactivateInstrument:
    return DeactivateInstrument(
        request.app.state.instrument_repository,
        request.app.state.event_bus,
    )
