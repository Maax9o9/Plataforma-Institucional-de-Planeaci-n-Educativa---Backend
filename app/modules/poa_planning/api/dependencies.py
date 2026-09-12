"""Composición del ejercicio anual."""

from fastapi import Request

from ..application.use_cases.create_structure import CreateExercise
from ..application.use_cases.manage_exercise import (
    ApproveExercise,
    CloseExercise,
    RejectExercise,
    SendExercise,
)


def get_create_exercise_use_case(request: Request) -> CreateExercise:
    return CreateExercise(request.app.state.poa_repository, request.app.state.event_bus)


def get_send_exercise_use_case(request: Request) -> SendExercise:
    return SendExercise(
        request.app.state.poa_repository,
        request.app.state.poa_form_repository,
        request.app.state.state_change_repository,
        request.app.state.event_bus,
    )


def get_approve_exercise_use_case(request: Request) -> ApproveExercise:
    return ApproveExercise(
        request.app.state.poa_repository,
        request.app.state.poa_form_repository,
        request.app.state.state_change_repository,
        request.app.state.event_bus,
    )


def get_reject_exercise_use_case(request: Request) -> RejectExercise:
    return RejectExercise(
        request.app.state.poa_repository,
        request.app.state.poa_form_repository,
        request.app.state.state_change_repository,
        request.app.state.event_bus,
    )


def get_close_exercise_use_case(request: Request) -> CloseExercise:
    return CloseExercise(
        request.app.state.poa_repository,
        request.app.state.poa_form_repository,
        request.app.state.state_change_repository,
        request.app.state.event_bus,
    )
