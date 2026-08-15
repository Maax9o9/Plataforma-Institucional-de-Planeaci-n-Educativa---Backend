"""Composicion de casos de uso de indicadores."""

from fastapi import Request

from ..application.use_cases.manage_indicator import (
    ChangeIndicatorPeriodicity,
    CreateBaseline,
    CreateGoal,
    DeactivateIndicator,
    UpdateIndicator,
)
from ..application.use_cases.register_indicator import RegisterIndicator


def get_register_indicator_use_case(request: Request) -> RegisterIndicator:
    return RegisterIndicator(
        repository=request.app.state.indicator_repository,
        area_reader=request.app.state.area_repository,
        user_reader=request.app.state.user_repository,
        instrument_reader=request.app.state.instrument_repository,
        indicator_type_reader=request.app.state.indicator_type_repository,
        event_bus=request.app.state.event_bus,
    )


def get_update_indicator_use_case(request: Request) -> UpdateIndicator:
    return UpdateIndicator(
        request.app.state.indicator_repository,
        request.app.state.area_repository,
        request.app.state.user_repository,
        request.app.state.event_bus,
    )


def get_deactivate_indicator_use_case(request: Request) -> DeactivateIndicator:
    return DeactivateIndicator(request.app.state.indicator_repository, request.app.state.event_bus)


def get_create_baseline_use_case(request: Request) -> CreateBaseline:
    return CreateBaseline(request.app.state.indicator_repository, request.app.state.event_bus)


def get_create_goal_use_case(request: Request) -> CreateGoal:
    return CreateGoal(
        request.app.state.indicator_repository,
        request.app.state.period_repository,
        request.app.state.event_bus,
    )


def get_change_periodicity_use_case(request: Request) -> ChangeIndicatorPeriodicity:
    return ChangeIndicatorPeriodicity(
        request.app.state.indicator_repository,
        request.app.state.event_bus,
    )
