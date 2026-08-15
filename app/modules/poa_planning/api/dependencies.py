"""Composicion de casos de uso de planeacion POA."""

from fastapi import Request

from ..application.use_cases.create_structure import (
    CreateActivity,
    CreateExercise,
    CreateObjective,
    CreateProcess,
    UpdateActivity,
)


def get_create_exercise_use_case(request: Request) -> CreateExercise:
    return CreateExercise(request.app.state.poa_repository, request.app.state.event_bus)


def get_create_process_use_case(request: Request) -> CreateProcess:
    return CreateProcess(
        request.app.state.poa_repository,
        request.app.state.area_repository,
        request.app.state.event_bus,
    )


def get_create_objective_use_case(request: Request) -> CreateObjective:
    return CreateObjective(request.app.state.poa_repository, request.app.state.event_bus)


def get_create_activity_use_case(request: Request) -> CreateActivity:
    return CreateActivity(
        request.app.state.poa_repository,
        request.app.state.user_repository,
        request.app.state.event_bus,
    )


def get_update_activity_use_case(request: Request) -> UpdateActivity:
    return UpdateActivity(
        request.app.state.poa_repository,
        request.app.state.poa_advance_repository,
        request.app.state.user_repository,
        request.app.state.event_bus,
    )
