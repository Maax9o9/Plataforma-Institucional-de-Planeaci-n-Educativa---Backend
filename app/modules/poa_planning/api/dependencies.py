"""Composición del ejercicio anual."""

from fastapi import Request

from ..application.use_cases.create_structure import CreateExercise


def get_create_exercise_use_case(request: Request) -> CreateExercise:
    return CreateExercise(request.app.state.poa_repository, request.app.state.event_bus)
