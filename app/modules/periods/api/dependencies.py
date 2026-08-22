"""Composicion de casos de uso de periodos."""

from fastapi import Request

from ..application.use_cases.change_period_status import ClosePeriod, OpenPeriod
from ..application.use_cases.create_period import CreatePeriod
from ..application.use_cases.reopen_period import ReopenPeriod


def get_create_period_use_case(request: Request) -> CreatePeriod:
    return CreatePeriod(
        request.app.state.period_repository,
        request.app.state.event_bus,
        request.app.state.unit_of_work,
    )


def get_open_period_use_case(request: Request) -> OpenPeriod:
    return OpenPeriod(
        request.app.state.period_repository,
        request.app.state.event_bus,
        request.app.state.unit_of_work,
    )


def get_close_period_use_case(request: Request) -> ClosePeriod:
    return ClosePeriod(
        request.app.state.period_repository,
        request.app.state.event_bus,
        request.app.state.unit_of_work,
    )


def get_reopen_period_use_case(request: Request) -> ReopenPeriod:
    return ReopenPeriod(
        request.app.state.period_repository,
        request.app.state.event_bus,
        request.app.state.capture_repository,
        request.app.state.poa_advance_repository,
        request.app.state.state_change_repository,
        request.app.state.unit_of_work,
    )
